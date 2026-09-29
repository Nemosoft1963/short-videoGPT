import json
import os
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from services.ffmpeg_service import run

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
URL_CACHE_DIR = STORAGE_DIR / "assets" / "inserts" / "_url_cache"
INSERT_URL_TIMEOUT = int(os.getenv("INSERT_URL_TIMEOUT", "45"))
INSERT_YOUTUBE_SECONDS = float(os.getenv("INSERT_YOUTUBE_SECONDS", "6"))
INSERT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
WARNING_KEYWORDS = (
    "餓死", "死亡", "死", "自殺", "破産", "倒産", "差押", "差し押さえ",
    "凍結", "危機", "警告", "号外", "緊急", "urgent", "crisis", "warning", "alert",
)

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def _safe_insert_id(video_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", (video_id or "").strip())


def _is_url(value: str) -> bool:
    return bool(re.match(r"https?://", value or "", re.IGNORECASE))


def _is_youtube_url(value: str) -> bool:
    if not _is_url(value):
        return False
    host = (urlparse(value).hostname or "").lower()
    return host in YOUTUBE_HOSTS or host.endswith(".youtube.com")


def _url_cache_key(url: str, suffix: str = "") -> str:
    payload = f"{url}|{suffix}".encode("utf-8")
    return sha256(payload).hexdigest()[:20]


def _extension_from_content_type(content_type: str, fallback: str) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
    }
    return mapping.get(content_type, fallback)


def _download_direct_url(url: str) -> Path | None:
    URL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS + IMAGE_EXTENSIONS:
        suffix = ""
    key = _url_cache_key(url)
    for ext in VIDEO_EXTENSIONS + IMAGE_EXTENSIONS:
        cached = URL_CACHE_DIR / f"{key}{ext}"
        if cached.exists():
            return cached

    try:
        request = Request(url, headers={"User-Agent": INSERT_USER_AGENT})
        with urlopen(request, timeout=INSERT_URL_TIMEOUT) as response:
            content_type = response.headers.get("Content-Type", "")
            suffix = suffix or _extension_from_content_type(content_type, "")
            if suffix not in VIDEO_EXTENSIONS + IMAGE_EXTENSIONS:
                print(f"[insert] URL is not a supported image/video asset: {url} ({content_type})")
                return None
            out_path = URL_CACHE_DIR / f"{key}{suffix}"
            with out_path.open("wb") as fh:
                shutil.copyfileobj(response, fh)
        return out_path
    except Exception as exc:
        print(f"[insert] URL download failed: {url} ({exc})")
        return None


def _download_youtube_intro(url: str) -> Path | None:
    URL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    duration = INSERT_YOUTUBE_SECONDS
    key = _url_cache_key(url, f"youtube:{duration}")
    clipped = URL_CACHE_DIR / f"{key}.mp4"
    if clipped.exists():
        return clipped

    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        print("[insert] yt-dlp is not installed; cannot fetch YouTube insert URL")
        return None

    downloaded = URL_CACHE_DIR / f"{key}_source.%(ext)s"
    try:
        subprocess.run([
            yt_dlp,
            "--no-playlist",
            "--no-warnings",
            "--force-overwrites",
            "--format", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
            "--output", str(downloaded),
            url,
        ], check=True, timeout=max(INSERT_URL_TIMEOUT, 120))
        sources = sorted(URL_CACHE_DIR.glob(f"{key}_source.*"))
        if not sources:
            print(f"[insert] yt-dlp produced no file for {url}")
            return None
        source = sources[0]
        run([
            "ffmpeg", "-y",
            "-i", source,
            "-t", str(duration),
            "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            clipped,
        ])
        return clipped
    except Exception as exc:
        print(f"[insert] YouTube intro download failed: {url} ({exc})")
        return None


def _candidate_files(video_id: str) -> list[Path]:
    safe_id = _safe_insert_id(video_id)
    raw_id = (video_id or "").strip()
    if not safe_id and not raw_id:
        return []

    names = []
    for name in (raw_id, safe_id):
        if name and name not in names:
            names.append(name)

    if safe_id and not safe_id.lower().endswith(VIDEO_EXTENSIONS + IMAGE_EXTENSIONS):
        names.extend(f"{safe_id}{ext}" for ext in VIDEO_EXTENSIONS + IMAGE_EXTENSIONS)
    if raw_id and raw_id != safe_id and not raw_id.lower().endswith(VIDEO_EXTENSIONS + IMAGE_EXTENSIONS):
        names.extend(f"{raw_id}{ext}" for ext in VIDEO_EXTENSIONS + IMAGE_EXTENSIONS)

    candidates: list[Path] = []
    for alias_file in (STORAGE_DIR / "inserts" / "aliases.json", STORAGE_DIR / "assets" / "inserts" / "aliases.json"):
        if not alias_file.exists():
            continue
        try:
            aliases = json.loads(alias_file.read_text(encoding="utf-8"))
            target = aliases.get(video_id) or aliases.get(safe_id)
        except Exception as exc:
            print(f"[insert] alias read failed: {alias_file} ({exc})")
            continue
        if target:
            target_path = Path(target)
            candidates.append(target_path if target_path.is_absolute() else STORAGE_DIR / target_path)

    candidates.append(STORAGE_DIR / "projects" / safe_id / "final" / "final.mp4")
    for name in names:
        candidates.extend([
            STORAGE_DIR / "inserts" / name,
            STORAGE_DIR / "assets" / "inserts" / name,
        ])
    return candidates


def resolve_insert_video(video_id: str) -> Path | None:
    if _is_youtube_url(video_id):
        return _download_youtube_intro(video_id)
    if _is_url(video_id):
        return _download_direct_url(video_id)

    for candidate in _candidate_files(video_id):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _wants_warning_layer(scene: dict, video_id: str) -> bool:
    explicit = (scene.get("insert_layer") or "").lower() in {"warning", "alert", "danger", "news"}
    if explicit:
        return True
    haystack = " ".join([
        video_id,
        scene.get("visual_prompt", ""),
        scene.get("narration", ""),
        scene.get("subtitle", ""),
        scene.get("overlay_text", ""),
    ]).lower()
    return any(keyword.lower() in haystack for keyword in WARNING_KEYWORDS)


def _overlay_position(position: str, width: int, height: int) -> tuple[str, str]:
    margin_x = 64 if width >= height else 48
    margin_y = 64 if width >= height else 280
    positions = {
        "top_right": (f"W-w-{margin_x}", f"{margin_x}"),
        "top_left": (f"{margin_x}", f"{margin_x}"),
        "bottom_left": (f"{margin_x}", f"H-h-{margin_y}"),
        "bottom_right": (f"W-w-{margin_x}", f"H-h-{margin_y}"),
    }
    return positions.get(position or "bottom_right", positions["bottom_right"])


def _center_warning_overlay_filter(width: int, height: int, fps: int) -> str:
    max_w = int(width * (0.72 if width >= height else 0.84))
    max_h = int(height * (0.62 if width >= height else 0.48))
    return (
        f"[1:v]scale={max_w}:{max_h}:force_original_aspect_ratio=decrease,"
        f"fps={fps},setsar=1,format=rgba,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0xFF1F2D@0.95:t=8:enable='lt(mod(t,0.55),0.28)',"
        "drawbox=x=10:y=10:w=iw-20:h=ih-20:color=0xFF1F2D@0.55:t=3:enable='lt(mod(t,0.55),0.28)',"
        "colorchannelmixer=aa=0.85[ins];"
        "[0:v][ins]overlay=x='(W-w)/2':y='(H-h)/2':shortest=1[over];"
        "[over]noise=alls=18:allf=t+u:enable='lt(mod(t,0.42),0.10)',"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0xFF1F2D@0.36:t=10:enable='lt(mod(t,0.70),0.12)',"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x00D7FF@0.18:t=3:enable='between(mod(t,0.90),0.18,0.24)'"
    )


def _corner_insert_filter(scene: dict, width: int, height: int, fps: int) -> str:
    insert_width = max(160, int(width * (0.25 if width >= height else 0.36)))
    x_expr, y_expr = _overlay_position(scene.get("insert_position", "bottom_right"), width, height)
    return (
        f"[1:v]scale={insert_width}:-2:force_original_aspect_ratio=decrease,"
        f"fps={fps},setsar=1,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0xF4EFE6@0.88:t=5,"
        "drawbox=x=8:y=8:w=iw-16:h=ih-16:color=0x111827@0.55:t=2[ins];"
        f"[0:v][ins]overlay=x='{x_expr}':y='{y_expr}':shortest=1"
    )


def apply_insert_overlay(base_video: Path, scene: dict, out_path: Path, width: int, height: int, fps: int) -> Path:
    video_id = (scene.get("insert_video_id") or "").strip()
    if not video_id:
        return base_video

    insert_video = resolve_insert_video(video_id)
    if not insert_video:
        print(f"[insert] source not found for insert:{video_id}; keeping base clip")
        return base_video

    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = float(scene.get("duration") or 6)
    warning_layer = _wants_warning_layer(scene, video_id)
    filter_complex = (
        _center_warning_overlay_filter(width, height, fps)
        if warning_layer
        else _corner_insert_filter(scene, width, height, fps)
    )
    input_args = ["-loop", "1", "-i", str(insert_video)] if _is_image(insert_video) else ["-stream_loop", "-1", "-i", str(insert_video)]
    run([
        "ffmpeg", "-y",
        "-i", base_video,
        *input_args,
        "-filter_complex", filter_complex,
        "-t", str(duration),
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ])
    return out_path
