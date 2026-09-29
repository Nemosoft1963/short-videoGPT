import base64
import hashlib
import json
import os
import re
import shutil
import time
import requests
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Callable

RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY", "")
RUNWAY_MODEL = os.getenv("RUNWAY_MODEL", "gen4_turbo")
RUNWAY_DURATION = int(os.getenv("RUNWAY_DURATION", "5"))
RUNWAY_RATIO = os.getenv("RUNWAY_RATIO", "720:1280")  # 縦型9:16
RUNWAY_IMAGE_RETRIES = int(os.getenv("RUNWAY_IMAGE_RETRIES", "3"))
POLL_SECONDS = int(os.getenv("COMFY_OUTPUT_POLL_SECONDS", "5"))
TIMEOUT_SECONDS = int(os.getenv("COMFY_OUTPUT_TIMEOUT_SECONDS", "300"))
RUNWAY_API_BASE = "https://api.dev.runwayml.com/v1"

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
IMAGE_CACHE_DIR = STORAGE_DIR / "assets" / "runway_cache"
VIDEO_CACHE_DIR = STORAGE_DIR / "assets" / "runway_video_cache"
RUNWAY_FUZZY_CACHE_THRESHOLD = float(os.getenv("RUNWAY_FUZZY_CACHE_THRESHOLD", "0.92"))
RUNWAY_SIMILAR_VIDEO_CACHE_ENABLED = os.getenv("RUNWAY_SIMILAR_VIDEO_CACHE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


class RunwayClient:
    def __init__(self):
        if not RUNWAY_API_KEY:
            raise RuntimeError("RUNWAY_API_KEY が設定されていません")
        self.headers = {
            "Authorization": f"Bearer {RUNWAY_API_KEY}",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06",
        }

    # ── キャッシュ ──────────────────────────────────────────────────

    @staticmethod
    def _prompt_hash(payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def _cache_key(self, prompt: str, ratio: str, duration: int | None = None, width: int | None = None, height: int | None = None) -> dict:
        return {
            "prompt": prompt.strip(),
            "model": RUNWAY_MODEL,
            "ratio": ratio,
            "duration": duration,
            "width": width,
            "height": height,
        }

    def _cache_path(self, prompt: str, ratio: str | None = None, width: int | None = None, height: int | None = None) -> Path:
        ratio = ratio or getattr(self, "_current_ratio", RUNWAY_RATIO)
        width = width if width is not None else getattr(self, "_current_width", None)
        height = height if height is not None else getattr(self, "_current_height", None)
        return IMAGE_CACHE_DIR / f"{self._prompt_hash(self._cache_key(prompt, ratio, width=width, height=height))}.jpg"

    def _video_cache_path(self, prompt: str, ratio: str | None = None, duration: int | None = None, width: int | None = None, height: int | None = None) -> Path:
        ratio = ratio or getattr(self, "_current_ratio", RUNWAY_RATIO)
        duration = duration if duration is not None else getattr(self, "_current_duration", RUNWAY_DURATION)
        width = width if width is not None else getattr(self, "_current_width", None)
        height = height if height is not None else getattr(self, "_current_height", None)
        return VIDEO_CACHE_DIR / f"{self._prompt_hash(self._cache_key(prompt, ratio, duration, width, height))}.mp4"

    @staticmethod
    def _video_meta_path(video_path: Path) -> Path:
        return video_path.with_suffix(".json")

    @staticmethod
    def _normalize_prompt_for_similarity(prompt: str) -> str:
        text = prompt.lower()
        boilerplate = (
            "photorealistic cinematic documentary footage",
            "natural lighting",
            "shallow depth of field",
            "subtle camera movement",
            "vertical 9:16",
            "no readable text",
        )
        for phrase in boilerplate:
            text = text.replace(phrase, " ")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @classmethod
    def _similarity_score(cls, left: str, right: str) -> tuple[float, float]:
        left_norm = cls._normalize_prompt_for_similarity(left)
        right_norm = cls._normalize_prompt_for_similarity(right)
        if not left_norm or not right_norm:
            return 0.0, 0.0
        left_tokens = set(left_norm.split())
        right_tokens = set(right_norm.split())
        token_union = left_tokens | right_tokens
        token_jaccard = len(left_tokens & right_tokens) / len(token_union) if token_union else 0.0
        sequence_ratio = SequenceMatcher(None, left_norm, right_norm).ratio()
        return (sequence_ratio * 0.7) + (token_jaccard * 0.3), token_jaccard

    def _write_video_cache_metadata(
        self,
        prompt: str,
        video_path: Path,
        ratio: str | None = None,
        duration: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        ratio = ratio or getattr(self, "_current_ratio", RUNWAY_RATIO)
        duration = duration if duration is not None else getattr(self, "_current_duration", RUNWAY_DURATION)
        width = width if width is not None else getattr(self, "_current_width", None)
        height = height if height is not None else getattr(self, "_current_height", None)
        payload = self._cache_key(prompt, ratio, duration, width, height)
        payload["video_file"] = video_path.name
        self._video_meta_path(video_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_similar_cached_video(
        self,
        prompt: str,
        ratio: str | None = None,
        duration: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> tuple[Path, float] | None:
        if not VIDEO_CACHE_DIR.exists():
            return None

        ratio = ratio or getattr(self, "_current_ratio", RUNWAY_RATIO)
        duration = duration if duration is not None else getattr(self, "_current_duration", RUNWAY_DURATION)
        width = width if width is not None else getattr(self, "_current_width", None)
        height = height if height is not None else getattr(self, "_current_height", None)

        best_match: tuple[Path, float] | None = None
        for meta_path in VIDEO_CACHE_DIR.glob("*.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if (
                meta.get("model") != RUNWAY_MODEL
                or meta.get("ratio") != ratio
                or meta.get("duration") != duration
                or meta.get("width") != width
                or meta.get("height") != height
            ):
                continue

            cached_prompt = str(meta.get("prompt") or "").strip()
            video_name = str(meta.get("video_file") or "")
            candidate = VIDEO_CACHE_DIR / video_name
            if not cached_prompt or not candidate.exists():
                continue

            score, token_jaccard = self._similarity_score(prompt, cached_prompt)
            if score < RUNWAY_FUZZY_CACHE_THRESHOLD or token_jaccard < 0.8:
                continue
            if best_match is None or score > best_match[1]:
                best_match = (candidate, score)

        return best_match

    def _load_cached_video(self, prompt: str, out_path: Path, ratio: str | None = None, duration: int | None = None, width: int | None = None, height: int | None = None) -> bool:
        """キャッシュ済み動画があれば out_path にコピーして True を返す。"""
        src = self._video_cache_path(prompt, ratio, duration, width, height)
        if not src.exists():
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out_path)
        if not self._video_meta_path(src).exists():
            self._write_video_cache_metadata(prompt, src, ratio, duration, width, height)
        print(f"[runway] 動画キャッシュヒット ({src.name}) → API呼び出しスキップ")
        return True

    def _load_similar_cached_video(self, prompt: str, out_path: Path, ratio: str | None = None, duration: int | None = None, width: int | None = None, height: int | None = None) -> bool:
        match = self._find_similar_cached_video(prompt, ratio, duration, width, height)
        if not match:
            return False
        src, score = match
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out_path)
        print(f"[runway] 近似動画キャッシュヒット({src.name}, score={score:.3f}) -> API呼び出しスキップ")
        return True

    def _save_video_cache(self, prompt: str, src_path: Path, ratio: str | None = None, duration: int | None = None, width: int | None = None, height: int | None = None) -> None:
        """生成した動画をキャッシュに保存する。"""
        VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dst = self._video_cache_path(prompt, ratio, duration, width, height)
        shutil.copy2(src_path, dst)
        self._write_video_cache_metadata(prompt, dst, ratio, duration, width, height)
        print(f"[runway] 動画キャッシュ保存: {dst.name}")

    def _load_cached_b64(self, prompt: str, ratio: str | None = None, width: int | None = None, height: int | None = None) -> Optional[str]:
        """キャッシュ済み画像を base64 data URL で返す。なければ None。"""
        p = self._cache_path(prompt, ratio, width, height)
        if not p.exists():
            return None
        data = base64.b64encode(p.read_bytes()).decode()
        print(f"[runway] キャッシュヒット ({p.name}) → 画像生成スキップ")
        return f"data:image/jpeg;base64,{data}"

    def _save_to_cache(self, prompt: str, url: str, ratio: str | None = None, width: int | None = None, height: int | None = None) -> None:
        """URL から画像をダウンロードしてキャッシュに保存する。"""
        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p = self._cache_path(prompt, ratio, width, height)
        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        with open(p, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[runway] 画像キャッシュ保存: {p.name}")

    # ── 公開メソッド ────────────────────────────────────────────────

    def generate_clip(
        self,
        positive_prompt: str,
        negative_prompt: str,
        out_path: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        ratio: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Path:
        ratio = ratio or RUNWAY_RATIO
        duration = RUNWAY_DURATION
        self._current_ratio = ratio
        self._current_duration = duration
        self._current_width = width
        self._current_height = height
        """プロンプトから動画を生成して out_path に保存する。
        同じプロンプトの画像がキャッシュにあれば画像生成をスキップする。
        """

        # 動画キャッシュチェック（ヒットすれば API 呼び出し不要）
        if self._load_cached_video(positive_prompt, out_path):
            if progress_callback:
                progress_callback(100, "Runway: キャッシュ動画使用、スキップ")
            return out_path

        # Step1: 画像生成（またはキャッシュ取得）
        if RUNWAY_SIMILAR_VIDEO_CACHE_ENABLED and self._load_similar_cached_video(positive_prompt, out_path):
            if progress_callback:
                progress_callback(100, "Runway: 近似キャッシュ動画使用、スキップ")
            return out_path

        cached_b64 = self._load_cached_b64(positive_prompt)
        if cached_b64:
            prompt_image = cached_b64
            if progress_callback:
                progress_callback(30, "Runway: キャッシュ画像使用、動画生成中...")
        else:
            if progress_callback:
                progress_callback(10, "Runway: 画像生成中...")
            print(f"[runway] Step1 画像生成: {positive_prompt[:60]}...")
            image_url = self._generate_image(positive_prompt)
            self._save_to_cache(positive_prompt, image_url)
            prompt_image = image_url
            if progress_callback:
                progress_callback(30, "Runway: 動画生成中...")

        # Step2: 画像→動画
        print(f"[runway] Step2 動画生成開始")
        payload = {
            "model": RUNWAY_MODEL,
            "promptImage": prompt_image,
            "promptText": positive_prompt,
            "ratio": ratio,
            "duration": duration,
        }

        r = requests.post(
            f"{RUNWAY_API_BASE}/image_to_video",
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        if not r.ok:
            body = r.text[:500]
            if r.status_code in (402, 429) or "credit" in body.lower() or "insufficient" in body.lower():
                raise RuntimeError(
                    f"Runway クレジット不足（残高確認: https://app.runwayml.com）: HTTP {r.status_code}"
                )
            raise RuntimeError(f"Runway API エラー HTTP {r.status_code}: {body}")

        task_id = r.json().get("id")
        if not task_id:
            raise RuntimeError(f"Runway API: task_id が返りませんでした: {r.text}")
        print(f"[runway] task_id: {task_id}")

        # ポーリング
        start = time.time()
        while time.time() - start < TIMEOUT_SECONDS:
            time.sleep(POLL_SECONDS)
            elapsed = int(time.time() - start)

            status_r = requests.get(
                f"{RUNWAY_API_BASE}/tasks/{task_id}",
                headers=self.headers,
                timeout=30,
            )
            if not status_r.ok:
                print(f"[runway] ステータス確認エラー: {status_r.status_code}")
                continue

            data = status_r.json()
            status = data.get("status", "")
            progress = data.get("progress", 0)
            print(f"[runway] status={status} progress={progress} elapsed={elapsed}s")

            if progress_callback:
                mapped = 30 + int(progress * 70)
                progress_callback(mapped, f"Runway動画生成中... {elapsed}秒経過")

            if status == "SUCCEEDED":
                output = data.get("output", [])
                if not output:
                    raise RuntimeError("Runway API: output が空です")
                video_url = output[0]
                print(f"[runway] ダウンロード: {video_url[:60]}...")
                self._download(video_url, out_path)
                self._save_video_cache(positive_prompt, out_path)
                return out_path

            elif status == "FAILED":
                error = data.get("failure", "不明なエラー")
                raise RuntimeError(f"Runway動画生成失敗: {error}")

        raise TimeoutError(f"Runway APIタイムアウト ({TIMEOUT_SECONDS}秒)")

    # ── 内部メソッド ────────────────────────────────────────────────

    @staticmethod
    def _is_retryable_error(error: str) -> bool:
        text = (error or "").lower()
        return any(
            marker in text
            for marker in (
                "unexpected error",
                "temporarily",
                "timeout",
                "timed out",
                "internal",
                "try again",
            )
        )

    def _generate_image_once(self, prompt: str, ratio: str | None = None) -> str:
        """テキストから画像を1回生成して URL を返す。"""
        payload = {
            "model": "gen4_image",
            "promptText": prompt,
            "ratio": ratio or getattr(self, "_current_ratio", RUNWAY_RATIO),
        }
        r = requests.post(
            f"{RUNWAY_API_BASE}/text_to_image",
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        if not r.ok:
            body = r.text[:500]
            if r.status_code in (402, 429) or "credit" in body.lower() or "insufficient" in body.lower():
                raise RuntimeError(
                    f"Runway クレジット不足（残高確認: https://app.runwayml.com）: HTTP {r.status_code}"
                )
            if 500 <= r.status_code < 600:
                raise RuntimeError(f"Runway 画像生成一時エラー HTTP {r.status_code}: {body}")
            raise RuntimeError(f"Runway 画像生成エラー HTTP {r.status_code}: {body}")

        task_id = r.json().get("id")
        if not task_id:
            raise RuntimeError(f"Runway 画像生成: task_id が返りませんでした: {r.text}")

        start = time.time()
        while time.time() - start < 120:
            time.sleep(3)
            status_r = requests.get(
                f"{RUNWAY_API_BASE}/tasks/{task_id}",
                headers=self.headers,
                timeout=30,
            )
            if not status_r.ok:
                continue
            data = status_r.json()
            status = data.get("status", "")
            if status == "SUCCEEDED":
                output = data.get("output", [])
                if not output:
                    raise RuntimeError("Runway 画像生成: output が空です")
                return output[0]
            elif status == "FAILED":
                error = data.get("failure", "不明なエラー")
                raise RuntimeError(f"Runway 画像生成失敗(task_id={task_id}): {error}")

        raise TimeoutError("Runway 画像生成タイムアウト")

    def _generate_image(self, prompt: str, ratio: str | None = None) -> str:
        attempts = max(1, RUNWAY_IMAGE_RETRIES)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                if attempt > 1:
                    print(f"[runway] 画像生成リトライ {attempt}/{attempts}", flush=True)
                return self._generate_image_once(prompt, ratio)
            except Exception as e:
                last_error = e
                message = str(e)
                if attempt >= attempts or not self._is_retryable_error(message):
                    raise
                wait = min(20, 2 ** attempt)
                print(f"[runway] 画像生成一時失敗: {message} / {wait}s 後に再試行", flush=True)
                time.sleep(wait)
        raise last_error or RuntimeError("Runway 画像生成失敗")

    def _download(self, url: str, out_path: Path) -> None:
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[runway] 保存完了: {out_path}")
