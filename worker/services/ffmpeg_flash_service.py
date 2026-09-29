import os
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from services.ffmpeg_service import normalize_clip

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
FLASH_DIR = STORAGE_DIR / "assets" / "flashes"
FLASH_DURATION = float(os.getenv("PHF_FLASH_DURATION", "0.7"))
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")


def _run(cmd: list[str]) -> None:
    print("FLASH RUN:", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def flash_cache_key(word: str, prompt: str, width: int, height: int, fps: int) -> str:
    payload = {
        "word": (word or "").strip(),
        "prompt": (prompt or "").strip(),
        "width": width,
        "height": height,
        "fps": fps,
        "duration": FLASH_DURATION,
        "version": "phf-v1",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _create_local_flash_base(out_path: Path, prompt: str, width: int, height: int, fps: int) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"geq="
        f"lum='clip(30+120*sin(2*PI*(X/{width}*1.7+T*7))+70*random(1),0,255)':"
        f"cb='128+30*sin(2*PI*T*12)':cr='150+55*sin(2*PI*(X/{width}+T*9))',"
        f"fps={fps},"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0xB8341C@0.22:t=fill,"
        f"drawbox=x=12+8*sin(2*PI*t*20):y=12:w=iw-24:h=ih-24:color=0xFF1F1F@0.78:t=6,"
        f"drawtext=fontfile='{FONT_BOLD}':text='{_escape((prompt or 'PHF')[:28])}':"
        f"fontsize={max(16, int(height * 0.035))}:fontcolor=0xFFFFFF@0.24:"
        f"x=(w-text_w)/2+20*sin(2*PI*t*18):y=h*0.72"
    )
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x090B10:s={width}x{height}:r={fps}",
        "-t", f"{FLASH_DURATION:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ])
    return out_path


def _burn_flash_text(base_path: Path, out_path: Path, word: str, width: int, height: int, fps: int) -> Path:
    font_size = max(56, int(height * 0.18))
    border = max(8, int(height * 0.018))
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},"
        f"eq=contrast=1.45:saturation=1.25,"
        f"noise=alls=28:allf=t+u,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0x000000@0.18:t=fill,"
        f"drawbox=x=20:y=20:w=iw-40:h=ih-40:color=0xFF0000@0.72:t={border},"
        f"drawtext=fontfile='{FONT_BOLD}':text='{_escape(word)}':"
        f"fontsize={font_size}:fontcolor=0xFFFFFF:"
        f"borderw={border}:bordercolor=0xB8341C@0.95:"
        f"x=(w-text_w)/2+12*sin(2*PI*t*18):"
        f"y=(h-text_h)/2+8*sin(2*PI*t*24),"
        f"fade=t=in:st=0:d=0.06,fade=t=out:st=0.88:d=0.12"
    )
    _run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(base_path),
        "-t", f"{FLASH_DURATION:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ])
    return out_path


def ensure_flash_visual_clip(
    out_path: Path,
    word: str,
    prompt: str,
    width: int,
    height: int,
    fps: int,
    video_client=None,
    use_runway: bool = False,
    negative_prompt: str = "",
    ratio: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Path:
    FLASH_DIR.mkdir(parents=True, exist_ok=True)
    key = flash_cache_key(word, prompt, width, height, fps)
    cached = FLASH_DIR / f"{key}.mp4"
    meta = FLASH_DIR / f"{key}.json"
    if cached.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, out_path)
        if progress_callback:
            progress_callback(100, "PHF: cached flash asset")
        return out_path

    work_dir = FLASH_DIR / f".work_{key}"
    work_dir.mkdir(parents=True, exist_ok=True)
    base_raw = work_dir / "base_raw.mp4"
    base_norm = work_dir / "base_norm.mp4"
    final_tmp = work_dir / "flash.mp4"

    if use_runway and video_client:
        if progress_callback:
            progress_callback(10, "PHF: Runway flash source")
        try:
            try:
                video_client.generate_clip(
                    prompt,
                    negative_prompt,
                    base_raw,
                    progress_callback=progress_callback,
                    ratio=ratio,
                    width=width,
                    height=height,
                )
            except TypeError:
                video_client.generate_clip(prompt, negative_prompt, base_raw, progress_callback=progress_callback)
        except Exception:
            if progress_callback:
                progress_callback(35, "PHF: Runway failed, using local flash")
            _create_local_flash_base(base_raw, prompt, width, height, fps)
    else:
        _create_local_flash_base(base_raw, prompt, width, height, fps)

    normalize_clip(base_raw, base_norm, width, height, fps, FLASH_DURATION)
    _burn_flash_text(base_norm, final_tmp, word, width, height, fps)
    shutil.copy2(final_tmp, cached)
    shutil.copy2(cached, out_path)
    meta.write_text(json.dumps({
        "word": word,
        "prompt": prompt,
        "width": width,
        "height": height,
        "fps": fps,
        "duration": FLASH_DURATION,
        "asset": str(cached),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def create_flash_sound(out_path: Path, duration: float = FLASH_DURATION) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.1, float(duration or FLASH_DURATION))
    filter_complex = (
        "[0:a]volume=0.90,afade=t=out:st=0.38:d=0.55[boom];"
        "[1:a]volume=0.18,atrim=0:1,afade=t=out:st=0.55:d=0.35[noise];"
        "[2:a]volume=0.16,afade=t=out:st=0.28:d=0.35[beep];"
        "[boom][noise][beep]amix=inputs=3:duration=longest:dropout_transition=0,"
        "alimiter=limit=0.92[a]"
    )
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=58:sample_rate=44100:duration={dur}",
        "-f", "lavfi", "-i", f"anoisesrc=color=white:sample_rate=44100:duration={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=2700:sample_rate=44100:duration={dur}",
        "-filter_complex", filter_complex,
        "-map", "[a]",
        "-t", f"{dur:.3f}",
        "-ar", "44100", "-ac", "2",
        str(out_path),
    ])
    return out_path
