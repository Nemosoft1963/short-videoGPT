import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

import requests


MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_API_BASE = os.getenv("MINIMAX_API_BASE", "https://api.minimax.io/v1").rstrip("/")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-Hailuo-2.3")
MINIMAX_DURATION = int(os.getenv("MINIMAX_DURATION", "6"))
MINIMAX_RESOLUTION = os.getenv("MINIMAX_RESOLUTION", "768P")
MINIMAX_PROMPT_OPTIMIZER = os.getenv("MINIMAX_PROMPT_OPTIMIZER", "true").lower() in {"1", "true", "yes", "on"}
MINIMAX_FAST_PRETREATMENT = os.getenv("MINIMAX_FAST_PRETREATMENT", "true").lower() in {"1", "true", "yes", "on"}
POLL_SECONDS = int(os.getenv("MINIMAX_POLL_SECONDS", "10"))
TIMEOUT_SECONDS = int(os.getenv("MINIMAX_TIMEOUT_SECONDS", "900"))

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
VIDEO_CACHE_DIR = STORAGE_DIR / "assets" / "minimax_video_cache"


class MiniMaxClient:
    def __init__(self):
        if not MINIMAX_API_KEY:
            raise RuntimeError("MINIMAX_API_KEY is not set")
        self.headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _prompt_hash(payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _compose_prompt(positive_prompt: str, negative_prompt: str, ratio: str | None, width: int | None, height: int | None) -> str:
        prompt = positive_prompt.strip()
        if ratio in {"9:16", "720:1280"} or (width and height and height > width):
            prompt = f"{prompt}\nVertical 9:16 composition, documentary style, no readable text."
        if negative_prompt.strip():
            prompt = f"{prompt}\nAvoid: {negative_prompt.strip()}"
        return prompt[:2000]

    def _cache_key(self, prompt: str, model: str, duration: int, resolution: str) -> dict:
        return {
            "prompt": prompt.strip(),
            "model": model,
            "duration": duration,
            "resolution": resolution,
            "prompt_optimizer": MINIMAX_PROMPT_OPTIMIZER,
            "fast_pretreatment": MINIMAX_FAST_PRETREATMENT,
        }

    def _video_cache_path(self, prompt: str, model: str, duration: int, resolution: str) -> Path:
        return VIDEO_CACHE_DIR / f"{self._prompt_hash(self._cache_key(prompt, model, duration, resolution))}.mp4"

    def _load_cached_video(self, cache_path: Path, out_path: Path) -> bool:
        if not cache_path.exists():
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_path, out_path)
        print(f"[minimax] video cache hit ({cache_path.name}) -> API skip")
        return True

    def _save_video_cache(self, cache_path: Path, src_path: Path, metadata: dict) -> None:
        VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, cache_path)
        cache_path.with_suffix(".json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[minimax] video cache saved: {cache_path.name}")

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
        model = MINIMAX_MODEL
        duration = MINIMAX_DURATION
        resolution = MINIMAX_RESOLUTION
        prompt = self._compose_prompt(positive_prompt, negative_prompt, ratio, width, height)
        cache_path = self._video_cache_path(prompt, model, duration, resolution)

        if self._load_cached_video(cache_path, out_path):
            if progress_callback:
                progress_callback(100, "MiniMax: cached video used")
            return out_path

        payload = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution,
            "prompt_optimizer": MINIMAX_PROMPT_OPTIMIZER,
            "fast_pretreatment": MINIMAX_FAST_PRETREATMENT,
        }

        if progress_callback:
            progress_callback(10, "MiniMax: generation request")
        r = requests.post(
            f"{MINIMAX_API_BASE}/video_generation",
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        if not r.ok:
            body = r.text[:800]
            if r.status_code in (401, 403):
                raise RuntimeError(f"MiniMax auth failed HTTP {r.status_code}: {body}")
            if r.status_code in (402, 429) or any(word in body.lower() for word in ("quota", "credit", "balance", "billing", "insufficient")):
                raise RuntimeError(f"MiniMax quota/billing issue HTTP {r.status_code}: {body}")
            raise RuntimeError(f"MiniMax API error HTTP {r.status_code}: {body}")

        data = r.json()
        task_id = data.get("task_id")
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") not in (None, 0):
            raise RuntimeError(f"MiniMax task rejected: {json.dumps(data, ensure_ascii=False)[:800]}")
        if not task_id:
            raise RuntimeError(f"MiniMax API did not return task_id: {r.text[:800]}")
        print(f"[minimax] task_id: {task_id}")

        file_id = self._poll_file_id(task_id, progress_callback)
        video_url = self._retrieve_download_url(file_id)
        self._download(video_url, out_path)
        self._save_video_cache(cache_path, out_path, {
            **self._cache_key(prompt, model, duration, resolution),
            "task_id": task_id,
            "file_id": file_id,
        })
        if progress_callback:
            progress_callback(100, "MiniMax: completed")
        return out_path

    def _poll_file_id(self, task_id: str, progress_callback: Optional[Callable[[int, str], None]]) -> str:
        start = time.time()
        while time.time() - start < TIMEOUT_SECONDS:
            time.sleep(POLL_SECONDS)
            elapsed = int(time.time() - start)
            r = requests.get(
                f"{MINIMAX_API_BASE}/query/video_generation",
                headers=self.headers,
                params={"task_id": task_id},
                timeout=30,
            )
            if not r.ok:
                print(f"[minimax] status error: HTTP {r.status_code} {r.text[:200]}")
                continue
            data = r.json()
            status = str(data.get("status") or "").lower()
            print(f"[minimax] status={status} elapsed={elapsed}s")
            if progress_callback:
                progress_callback(min(95, 15 + elapsed // 4), f"MiniMax: generating... {elapsed}s")

            if status == "success":
                file_id = str(data.get("file_id") or "")
                if not file_id:
                    raise RuntimeError(f"MiniMax succeeded without file_id: {json.dumps(data, ensure_ascii=False)[:800]}")
                return file_id
            if status == "fail":
                reason = data.get("error_message") or (data.get("base_resp") or {}).get("status_msg") or "unknown error"
                raise RuntimeError(f"MiniMax generation failed: {reason}")

        raise TimeoutError(f"MiniMax generation timeout ({TIMEOUT_SECONDS}s)")

    def _retrieve_download_url(self, file_id: str) -> str:
        r = requests.get(
            f"{MINIMAX_API_BASE}/files/retrieve",
            headers=self.headers,
            params={"file_id": file_id},
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(f"MiniMax file retrieve error HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        url = (data.get("file") or {}).get("download_url")
        if not url:
            raise RuntimeError(f"MiniMax file retrieve did not return download_url: {json.dumps(data, ensure_ascii=False)[:800]}")
        return url

    def _download(self, url: str, out_path: Path) -> None:
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[minimax] saved: {out_path}")
