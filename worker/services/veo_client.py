import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

import requests


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
VEO_API_BASE = os.getenv("VEO_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")
VEO_DURATION_SECONDS = os.getenv("VEO_DURATION_SECONDS", "6")
VEO_RESOLUTION = os.getenv("VEO_RESOLUTION", "720p")
VEO_PERSON_GENERATION = os.getenv("VEO_PERSON_GENERATION", "").strip()
POLL_SECONDS = int(os.getenv("VEO_POLL_SECONDS", os.getenv("COMFY_OUTPUT_POLL_SECONDS", "10")))
TIMEOUT_SECONDS = int(os.getenv("VEO_TIMEOUT_SECONDS", os.getenv("COMFY_OUTPUT_TIMEOUT_SECONDS", "900")))

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
VIDEO_CACHE_DIR = STORAGE_DIR / "assets" / "veo_lite_video_cache"


class VeoLiteClient:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
        self.headers = {
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _prompt_hash(payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _aspect_ratio(ratio: str | None, width: int | None, height: int | None) -> str:
        if ratio:
            normalized = ratio.strip()
            if normalized == "720:1280":
                return "9:16"
            if normalized == "1280:720":
                return "16:9"
            if normalized in {"9:16", "16:9"}:
                return normalized
        if width and height and height > width:
            return "9:16"
        return "16:9"

    @staticmethod
    def _duration_seconds() -> int:
        duration = str(VEO_DURATION_SECONDS).strip().replace("s", "")
        return int(duration) if duration in {"4", "6", "8"} else 6

    @staticmethod
    def _resolution() -> str:
        resolution = str(VEO_RESOLUTION).strip().lower()
        return resolution if resolution in {"720p", "1080p"} else "720p"

    def _cache_key(
        self,
        prompt: str,
        negative_prompt: str,
        aspect_ratio: str,
        duration_seconds: int,
        resolution: str,
    ) -> dict:
        return {
            "prompt": prompt.strip(),
            "negative_prompt": negative_prompt.strip(),
            "model": VEO_MODEL,
            "aspect_ratio": aspect_ratio,
            "duration_seconds": duration_seconds,
            "resolution": resolution,
        }

    def _video_cache_path(
        self,
        prompt: str,
        negative_prompt: str,
        aspect_ratio: str,
        duration_seconds: int,
        resolution: str,
    ) -> Path:
        key = self._prompt_hash(self._cache_key(prompt, negative_prompt, aspect_ratio, duration_seconds, resolution))
        return VIDEO_CACHE_DIR / f"{key}.mp4"

    def _load_cached_video(self, cache_path: Path, out_path: Path) -> bool:
        if not cache_path.exists():
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_path, out_path)
        print(f"[veo-lite] video cache hit ({cache_path.name}) -> API skip")
        return True

    def _save_video_cache(self, cache_path: Path, src_path: Path, metadata: dict) -> None:
        VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, cache_path)
        cache_path.with_suffix(".json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[veo-lite] video cache saved: {cache_path.name}")

    @staticmethod
    def _extract_video_uri(data: dict) -> str:
        samples = (
            data.get("response", {})
            .get("generateVideoResponse", {})
            .get("generatedSamples", [])
        )
        if samples:
            video = samples[0].get("video") or {}
            return video.get("uri") or ""

        generated = data.get("response", {}).get("generatedVideos", [])
        if generated:
            video = generated[0].get("video") or {}
            return video.get("uri") or video.get("downloadUri") or ""

        return ""

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
        duration_seconds = self._duration_seconds()
        resolution = self._resolution()
        if resolution == "1080p" and duration_seconds != 8:
            duration_seconds = 8

        cache_path = self._video_cache_path(positive_prompt, negative_prompt, aspect_ratio, duration_seconds, resolution)
        if self._load_cached_video(cache_path, out_path):
            if progress_callback:
                progress_callback(100, "Veo Lite: cached video used")
            return out_path

        prompt = positive_prompt.strip()
        if negative_prompt.strip():
            prompt = f"{prompt}\nAvoid: {negative_prompt.strip()}"

        parameters = {
            "aspectRatio": aspect_ratio,
            "durationSeconds": duration_seconds,
            "resolution": resolution,
        }
        if VEO_PERSON_GENERATION:
            parameters["personGeneration"] = VEO_PERSON_GENERATION

        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": parameters,
        }

        if progress_callback:
            progress_callback(10, "Veo Lite: generation request")
        r = requests.post(
            f"{VEO_API_BASE}/models/{VEO_MODEL}:predictLongRunning",
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        if not r.ok:
            body = r.text[:500]
            if r.status_code in (400, 401, 403):
                raise RuntimeError(f"Veo Lite auth or request issue HTTP {r.status_code}: {body}")
            if r.status_code in (402, 429) or "quota" in body.lower() or "billing" in body.lower():
                raise RuntimeError(f"Veo Lite quota/billing issue HTTP {r.status_code}: {body}")
            raise RuntimeError(f"Veo Lite API error HTTP {r.status_code}: {body}")

        operation = r.json()
        operation_name = operation.get("name")
        if not operation_name:
            raise RuntimeError(f"Veo Lite API did not return operation name: {r.text[:500]}")
        print(f"[veo-lite] operation: {operation_name}")

        start = time.time()
        while time.time() - start < TIMEOUT_SECONDS:
            time.sleep(POLL_SECONDS)
            elapsed = int(time.time() - start)
            status_r = requests.get(
                f"{VEO_API_BASE}/{operation_name}",
                headers={"x-goog-api-key": GEMINI_API_KEY},
                timeout=30,
            )
            if not status_r.ok:
                print(f"[veo-lite] status error: {status_r.status_code}")
                continue

            data = status_r.json()
            done = bool(data.get("done"))
            print(f"[veo-lite] done={done} elapsed={elapsed}s")
            if progress_callback:
                progress_callback(min(95, 15 + elapsed // 5), f"Veo Lite: generating... {elapsed}s")

            if not done:
                continue

            if data.get("error"):
                raise RuntimeError(f"Veo Lite generation failed: {json.dumps(data['error'], ensure_ascii=False)[:500]}")

            video_uri = self._extract_video_uri(data)
            if not video_uri:
                raise RuntimeError(f"Veo Lite completed without video URI: {json.dumps(data, ensure_ascii=False)[:800]}")

            self._download(video_uri, out_path)
            self._save_video_cache(cache_path, out_path, {
                **self._cache_key(positive_prompt, negative_prompt, aspect_ratio, duration_seconds, resolution),
                "operation_name": operation_name,
            })
            if progress_callback:
                progress_callback(100, "Veo Lite: completed")
            return out_path

        raise TimeoutError(f"Veo Lite generation timeout ({TIMEOUT_SECONDS}s)")

    def _download(self, url: str, out_path: Path) -> None:
        r = requests.get(url, headers={"x-goog-api-key": GEMINI_API_KEY}, timeout=300, stream=True, allow_redirects=True)
        r.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[veo-lite] saved: {out_path}")
