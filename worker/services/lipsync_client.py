import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import requests


STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
LIPSYNC_URL = os.getenv("LIPSYNC_URL", "http://host.docker.internal:7860").rstrip("/")
LIPSYNC_ENDPOINT = os.getenv("LIPSYNC_ENDPOINT", "/generate")
LIPSYNC_TIMEOUT_SECONDS = float(os.getenv("LIPSYNC_TIMEOUT_SECONDS", "1800"))
LIPSYNC_SOURCE_PATH = os.getenv("LIPSYNC_ANALYSTK_SOURCE", "")
LIPSYNC_SOURCE_MODE = os.getenv("LIPSYNC_ANALYSTK_SOURCE_MODE", "image").strip().lower()
LIPSYNC_SOURCE_SET = os.getenv("LIPSYNC_ANALYSTK_SOURCE_SET", "anime").strip().lower()
LIPSYNC_IMAGE_SOURCE_PATH = os.getenv("LIPSYNC_ANALYSTK_IMAGE_SOURCE", "")
LIPSYNC_VIDEO_SOURCE_PATH = os.getenv("LIPSYNC_ANALYSTK_VIDEO_SOURCE", "")
LIPSYNC_ANIME_IMAGE_SOURCE_PATH = os.getenv("LIPSYNC_ANALYSTK_ANIME_IMAGE_SOURCE", LIPSYNC_IMAGE_SOURCE_PATH)
LIPSYNC_ANIME_VIDEO_SOURCE_PATH = os.getenv("LIPSYNC_ANALYSTK_ANIME_VIDEO_SOURCE", LIPSYNC_VIDEO_SOURCE_PATH)
LIPSYNC_REAL_IMAGE_SOURCE_PATH = os.getenv("LIPSYNC_ANALYSTK_REAL_IMAGE_SOURCE", "")
LIPSYNC_REAL_VIDEO_SOURCE_PATH = os.getenv("LIPSYNC_ANALYSTK_REAL_VIDEO_SOURCE", "")
LIPSYNC_CACHE_DIR = STORAGE_DIR / "assets" / "lipsync_cache"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv"}


def _truthy(value: str | None) -> bool:
    return (value or "").lower() not in {"", "0", "false", "no", "off"}


def lipsync_enabled() -> bool:
    return _truthy(os.getenv("LIPSYNC_ENABLED", "false"))


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(source: Path, audio: Path, width: int, height: int, fps: int, duration: float) -> str:
    payload = {
        "source": str(source),
        "source_sha": _file_digest(source),
        "audio_sha": _file_digest(audio),
        "width": width,
        "height": height,
        "fps": fps,
        "duration": round(float(duration), 3),
        "url": LIPSYNC_URL,
        "endpoint": LIPSYNC_ENDPOINT,
        "version": 4,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _resolve_configured_path(raw_path: str) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = STORAGE_DIR / path
    return path if path.exists() else None


def _source_matches_mode(path: Path, mode: str) -> bool:
    suffix = path.suffix.lower()
    if mode == "image":
        return suffix in IMAGE_SUFFIXES
    if mode == "video":
        return suffix in VIDEO_SUFFIXES
    return suffix in IMAGE_SUFFIXES | VIDEO_SUFFIXES


def _source_paths_for_set(source_set: str | None) -> tuple[str, str]:
    selected = (source_set or LIPSYNC_SOURCE_SET or "anime").strip().lower()
    if selected == "real":
        return LIPSYNC_REAL_IMAGE_SOURCE_PATH, LIPSYNC_REAL_VIDEO_SOURCE_PATH
    return LIPSYNC_ANIME_IMAGE_SOURCE_PATH, LIPSYNC_ANIME_VIDEO_SOURCE_PATH


def _resolve_lipsync_source(fallback_source_path: Path) -> Path:
    return _resolve_lipsync_source_for_mode(fallback_source_path, LIPSYNC_SOURCE_MODE, LIPSYNC_SOURCE_SET)


def _resolve_lipsync_source_for_mode(
    fallback_source_path: Path,
    source_mode: str | None = None,
    source_set: str | None = None,
) -> Path:
    raw_mode = (source_mode or LIPSYNC_SOURCE_MODE or "image").strip().lower()
    mode = raw_mode if raw_mode in {"image", "video", "auto"} else "image"
    image_source_path, video_source_path = _source_paths_for_set(source_set)
    candidates: list[Path | None] = []
    if mode == "video":
        candidates = [
            _resolve_configured_path(video_source_path),
            _resolve_configured_path(LIPSYNC_SOURCE_PATH),
            _resolve_configured_path(image_source_path),
        ]
    elif mode == "auto":
        candidates = [
            _resolve_configured_path(video_source_path),
            _resolve_configured_path(image_source_path),
            _resolve_configured_path(LIPSYNC_SOURCE_PATH),
        ]
    else:
        candidates = [
            _resolve_configured_path(image_source_path),
            _resolve_configured_path(LIPSYNC_SOURCE_PATH),
            _resolve_configured_path(video_source_path),
        ]

    for candidate in candidates:
        if candidate and _source_matches_mode(candidate, mode):
            return candidate
    return fallback_source_path


def _resolve_response_file(response: requests.Response, out_path: Path) -> bool:
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        out_path.write_bytes(response.content)
        return out_path.exists() and out_path.stat().st_size > 0

    data: dict[str, Any] = response.json()
    path_value = data.get("path") or data.get("output_path") or data.get("video_path")
    if path_value:
        source = Path(path_value)
        if not source.is_absolute():
            source = STORAGE_DIR / source
        if source.exists():
            shutil.copy2(source, out_path)
            return True

    url = data.get("url") or data.get("video_url") or data.get("download_url")
    if url:
        download = requests.get(url, timeout=LIPSYNC_TIMEOUT_SECONDS)
        download.raise_for_status()
        out_path.write_bytes(download.content)
        return out_path.exists() and out_path.stat().st_size > 0

    return False


def generate_lipsync_clip(
    *,
    audio_path: Path,
    fallback_source_path: Path,
    out_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
    speaker: str = "AnalystK",
    source_mode: str | None = None,
    source_set: str | None = None,
) -> bool:
    if not lipsync_enabled():
        return False
    if not audio_path.exists() or not fallback_source_path.exists():
        return False

    source_path = _resolve_lipsync_source_for_mode(fallback_source_path, source_mode, source_set)
    print(f"[lipsync] source selected: speaker={speaker} mode={source_mode or LIPSYNC_SOURCE_MODE} set={source_set or LIPSYNC_SOURCE_SET} path={source_path}")

    LIPSYNC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = LIPSYNC_CACHE_DIR / f"{_cache_key(source_path, audio_path, width, height, fps, duration)}.mp4"
    if cached.exists() and cached.stat().st_size > 0:
        shutil.copy2(cached, out_path)
        print(f"[lipsync] cache hit: {cached.name}")
        return True

    endpoint = f"{LIPSYNC_URL}{LIPSYNC_ENDPOINT if LIPSYNC_ENDPOINT.startswith('/') else '/' + LIPSYNC_ENDPOINT}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "speaker": speaker,
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "mode": "high_precision",
    }
    with source_path.open("rb") as source_file, audio_path.open("rb") as audio_file:
        response = requests.post(
            endpoint,
            data={key: str(value) for key, value in metadata.items()},
            files={
                "source": (source_path.name, source_file, "application/octet-stream"),
                "audio": (audio_path.name, audio_file, "audio/wav"),
            },
            timeout=LIPSYNC_TIMEOUT_SECONDS,
        )
    response.raise_for_status()
    if not _resolve_response_file(response, out_path):
        raise RuntimeError("lipsync service did not return a video")
    shutil.copy2(out_path, cached)
    print(f"[lipsync] generated: {out_path}")
    return True
