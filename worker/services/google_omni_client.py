"""Gemini Omni Flash image-to-video client for registered start frames."""
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

import requests


API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
API_BASE = os.getenv("GOOGLE_OMNI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
MODEL = os.getenv("GOOGLE_OMNI_MODEL", "gemini-omni-1.2-flash")
DURATION = max(3, min(15, int(os.getenv("GOOGLE_OMNI_DURATION_SECONDS", "6"))))
RESOLUTION = os.getenv("GOOGLE_OMNI_RESOLUTION", "720p")
TIMEOUT = int(os.getenv("GOOGLE_OMNI_TIMEOUT_SECONDS", "900"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
CACHE_DIR = STORAGE_DIR / "assets" / "google_omni_video_cache"


class GoogleOmniClient:
    def __init__(self):
        if not API_KEY:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
        self.headers = {"x-goog-api-key": API_KEY, "Content-Type": "application/json"}

    @staticmethod
    def _aspect_ratio(ratio: str | None, width: int | None, height: int | None) -> str:
        if ratio in {"9:16", "720:1280"}:
            return "9:16"
        if ratio in {"16:9", "1280:720"}:
            return "16:9"
        return "9:16" if width and height and height > width else "16:9"

    @staticmethod
    def _video_output(data: dict) -> tuple[str, str]:
        for step in reversed(data.get("steps") or []):
            if step.get("type") != "model_output":
                continue
            for item in step.get("content") or []:
                if item.get("type") == "video":
                    return item.get("data") or "", item.get("uri") or ""
        video = data.get("output_video") or {}
        return video.get("data") or "", video.get("uri") or ""

    def generate_clip(
        self,
        positive_prompt: str,
        negative_prompt: str,
        out_path: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        ratio: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        first_frame_image: Optional[Path] = None,
    ) -> Path:
        if first_frame_image is None:
            raise ValueError("Google Omni requires a registered start-frame image")
        image_path = Path(first_frame_image)
        mime_type = mimetypes.guess_type(image_path.name)[0]
        if mime_type not in {"image/jpeg", "image/png", "image/webp"} or not image_path.is_file():
            raise ValueError("first_frame_image must be an existing JPG, PNG, or WEBP file")
        image_bytes = image_path.read_bytes()
        if len(image_bytes) > 20 * 1024 * 1024:
            raise ValueError("first_frame_image exceeds 20 MB")
        aspect_ratio = self._aspect_ratio(ratio, width, height)
        prompt = positive_prompt.strip()
        prompt += "\nUse the supplied image as the opening frame. Preserve the same character, face, clothing, illustration style, and room. Animate only the described natural movements. Keep the camera stable. No generated speech, captions, or music."
        if negative_prompt.strip():
            prompt += f"\nAvoid: {negative_prompt.strip()}"
        cache_payload = {
            "model": MODEL,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": RESOLUTION,
            "duration": DURATION,
        }
        digest = hashlib.sha256(json.dumps(cache_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        cache_path = CACHE_DIR / f"{digest}.mp4"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            shutil.copy2(cache_path, out_path)
            if progress_callback:
                progress_callback(100, "Google Omni: cached video used")
            return out_path

        request = {
            "model": MODEL,
            "input": [
                {"type": "image", "data": base64.b64encode(image_bytes).decode("ascii"), "mime_type": mime_type},
                {"type": "text", "text": prompt},
            ],
            "generation_config": {"video_config": {"task": "image_to_video"}},
            "response_format": {
                "type": "video", "aspect_ratio": aspect_ratio,
                "resolution": RESOLUTION, "duration": f"{DURATION}s",
            },
        }
        if progress_callback:
            progress_callback(10, "Google Omni: generation request")
        try:
            response = requests.post(
                f"{API_BASE}/interactions", headers=self.headers, json=request,
                timeout=(20, TIMEOUT),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Google Omni request interrupted; do not retry automatically: {exc}") from exc
        if not response.ok:
            body = response.text[:500]
            raise RuntimeError(f"Google Omni API HTTP {response.status_code}: {body}")
        data = response.json()
        started = time.monotonic()
        while data.get("status") in {"in_progress", "queued"} and data.get("id"):
            if time.monotonic() - started > TIMEOUT:
                raise TimeoutError(f"Google Omni interaction {data['id']} exceeded {TIMEOUT}s; do not retry automatically")
            time.sleep(10)
            poll = requests.get(f"{API_BASE}/interactions/{data['id']}", headers=self.headers, timeout=30)
            poll.raise_for_status()
            data = poll.json()
            if progress_callback:
                progress_callback(min(95, 15 + int((time.monotonic() - started) / 10)), "Google Omni: generating")
        if data.get("status") in {"failed", "cancelled"} or data.get("error"):
            raise RuntimeError(f"Google Omni generation failed: {json.dumps(data.get('error') or data, ensure_ascii=False)[:500]}")
        video_data, video_uri = self._video_output(data)
        if video_data:
            out_path.write_bytes(base64.b64decode(video_data, validate=True))
        elif video_uri:
            with requests.get(video_uri, headers={"x-goog-api-key": API_KEY}, stream=True, timeout=300) as download:
                download.raise_for_status()
                with out_path.open("wb") as file:
                    for chunk in download.iter_content(chunk_size=1024 * 1024):
                        file.write(chunk)
        else:
            raise RuntimeError(f"Google Omni returned no video (status={data.get('status')}, id={data.get('id')})")
        if out_path.stat().st_size < 100_000:
            out_path.unlink(missing_ok=True)
            raise RuntimeError("Google Omni returned an invalid or empty video")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_path, cache_path)
        cache_path.with_suffix(".json").write_text(json.dumps(cache_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if progress_callback:
            progress_callback(100, "Google Omni: completed")
        return out_path
