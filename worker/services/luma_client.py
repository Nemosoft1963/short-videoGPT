import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

import requests

LUMA_API_KEY = os.getenv("LUMAAI_API_KEY", "") or os.getenv("LUMA_API_KEY", "")
LUMA_MODEL = os.getenv("LUMA_MODEL", "ray-flash-2")
LUMA_DURATION = os.getenv("LUMA_DURATION", "5s")
LUMA_RESOLUTION = os.getenv("LUMA_RESOLUTION", "720p")
LUMA_API_BASE = os.getenv("LUMA_API_BASE", "https://api.lumalabs.ai/dream-machine/v1").rstrip("/")
POLL_SECONDS = int(os.getenv("LUMA_POLL_SECONDS", os.getenv("COMFY_OUTPUT_POLL_SECONDS", "5")))
TIMEOUT_SECONDS = int(os.getenv("LUMA_TIMEOUT_SECONDS", os.getenv("COMFY_OUTPUT_TIMEOUT_SECONDS", "300")))

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
VIDEO_CACHE_DIR = STORAGE_DIR / "assets" / "luma_video_cache"


class LumaClient:
    def __init__(self):
        if not LUMA_API_KEY:
            raise RuntimeError("LUMAAI_API_KEY or LUMA_API_KEY is not set")
        self.headers = {
            "Authorization": f"Bearer {LUMA_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _prompt_hash(payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _aspect_ratio(ratio: str | None, width: int | None, height: int | None) -> str:
        if ratio:
            ratio = ratio.replace(":", ":").strip()
            if ratio in {"9:16", "16:9", "1:1", "4:3", "3:4", "21:9", "9:21"}:
                return ratio
            if ratio == "720:1280":
                return "9:16"
            if ratio == "1280:720":
                return "16:9"
        if width and height and height > width:
            return "9:16"
        return "16:9"

    def _cache_key(
        self,
        prompt: str,
        negative_prompt: str,
        aspect_ratio: str,
        duration: str,
        resolution: str,
    ) -> dict:
        return {
            "prompt": prompt.strip(),
            "negative_prompt": negative_prompt.strip(),
            "model": LUMA_MODEL,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
        }

    def _video_cache_path(
        self,
        prompt: str,
        negative_prompt: str,
        aspect_ratio: str,
        duration: str,
        resolution: str,
    ) -> Path:
        return VIDEO_CACHE_DIR / f"{self._prompt_hash(self._cache_key(prompt, negative_prompt, aspect_ratio, duration, resolution))}.mp4"

    def _load_cached_video(self, cache_path: Path, out_path: Path) -> bool:
        if not cache_path.exists():
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_path, out_path)
        print(f"[luma] video cache hit ({cache_path.name}) -> API skip")
        return True

    def _save_video_cache(self, cache_path: Path, src_path: Path, metadata: dict) -> None:
        VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, cache_path)
        cache_path.with_suffix(".json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[luma] video cache saved: {cache_path.name}")

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
        aspect_ratio = self._aspect_ratio(ratio, width, height)
        duration = LUMA_DURATION
        resolution = LUMA_RESOLUTION
        cache_path = self._video_cache_path(positive_prompt, negative_prompt, aspect_ratio, duration, resolution)
        if self._load_cached_video(cache_path, out_path):
            if progress_callback:
                progress_callback(100, "Luma: cached video used")
            return out_path

        prompt = positive_prompt.strip()
        if negative_prompt.strip():
            prompt = f"{prompt}\nAvoid: {negative_prompt.strip()}"
        payload = {
            "prompt": prompt,
            "model": LUMA_MODEL,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
        }

        if progress_callback:
            progress_callback(10, "Luma: generation request")
        r = requests.post(
            f"{LUMA_API_BASE}/generations",
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        if not r.ok:
            body = r.text[:500]
            if r.status_code in (402, 429) or "credit" in body.lower() or "billing" in body.lower():
                raise RuntimeError(f"Luma credit or rate limit issue HTTP {r.status_code}: {body}")
            raise RuntimeError(f"Luma API error HTTP {r.status_code}: {body}")

        generation = r.json()
        generation_id = generation.get("id")
        if not generation_id:
            raise RuntimeError(f"Luma API did not return generation id: {r.text}")
        print(f"[luma] generation_id: {generation_id}")

        start = time.time()
        while time.time() - start < TIMEOUT_SECONDS:
            time.sleep(POLL_SECONDS)
            elapsed = int(time.time() - start)
            status_r = requests.get(
                f"{LUMA_API_BASE}/generations/{generation_id}",
                headers=self.headers,
                timeout=30,
            )
            if not status_r.ok:
                print(f"[luma] status error: {status_r.status_code}")
                continue

            data = status_r.json()
            state = str(data.get("state") or "").lower()
            print(f"[luma] state={state} elapsed={elapsed}s")
            if progress_callback:
                progress_callback(min(95, 15 + elapsed // 3), f"Luma: generating... {elapsed}s")

            if state == "completed":
                video_url = (data.get("assets") or {}).get("video")
                if not video_url:
                    raise RuntimeError(f"Luma completed without video asset: {json.dumps(data, ensure_ascii=False)[:500]}")
                self._download(video_url, out_path)
                self._save_video_cache(cache_path, out_path, {
                    **self._cache_key(positive_prompt, negative_prompt, aspect_ratio, duration, resolution),
                    "generation_id": generation_id,
                })
                if progress_callback:
                    progress_callback(100, "Luma: completed")
                return out_path
            if state == "failed":
                reason = data.get("failure_reason") or data.get("error") or "unknown error"
                raise RuntimeError(f"Luma generation failed: {reason}")

        raise TimeoutError(f"Luma generation timeout ({TIMEOUT_SECONDS}s)")

    def _download(self, url: str, out_path: Path) -> None:
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[luma] saved: {out_path}")
