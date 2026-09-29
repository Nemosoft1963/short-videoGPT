import os
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse


APP_VERSION = "0.1.2"
WORK_DIR = Path(os.getenv("LIPSYNC_WORK_DIR", "/storage/lipsync_jobs"))
OUTPUT_NAME = "output.mp4"
PROVIDER = os.getenv("LIPSYNC_PROVIDER", "command").lower()
COMMAND_TEMPLATE = os.getenv("LIPSYNC_COMMAND_TEMPLATE", "").strip()
WAV2LIP_DIR = Path(os.getenv("WAV2LIP_DIR", "/opt/Wav2Lip"))
WAV2LIP_CHECKPOINT = os.getenv("WAV2LIP_CHECKPOINT", "")
WAV2LIP_FACE_DET_BATCH_SIZE = os.getenv("WAV2LIP_FACE_DET_BATCH_SIZE", "4")
WAV2LIP_BATCH_SIZE = os.getenv("WAV2LIP_BATCH_SIZE", "16")
MAX_UPLOAD_MB = int(os.getenv("LIPSYNC_MAX_UPLOAD_MB", "512"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("LIPSYNC_REQUEST_TIMEOUT_SECONDS", "1800"))
PORTRAIT_NORMALIZE_MODE = os.getenv("LIPSYNC_PORTRAIT_NORMALIZE_MODE", "letterbox").strip().lower()
PORTRAIT_BACKGROUND_COLOR = os.getenv("LIPSYNC_PORTRAIT_BACKGROUND_COLOR", "0x05070d")


app = FastAPI(title="AnalystK LipSync Service", version=APP_VERSION)


def _safe_suffix(filename: str, default: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".mkv", ".wav"} else default


def _copy_upload(upload: UploadFile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    limit = MAX_UPLOAD_MB * 1024 * 1024
    with path.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > limit:
                raise HTTPException(status_code=413, detail=f"upload too large; limit={MAX_UPLOAD_MB}MB")
            f.write(chunk)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print("[lipsync-service] run:", " ".join(shlex.quote(x) for x in cmd), flush=True)
    subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _normalize_video(input_path: Path, output_path: Path, width: int, height: int, fps: int, duration: float) -> None:
    if height > width and PORTRAIT_NORMALIZE_MODE in {"letterbox", "pad", "solid"}:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={PORTRAIT_BACKGROUND_COLOR},"
            f"setsar=1,fps={fps}"
        )
        _run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(input_path),
            "-t", str(max(0.1, duration)),
            "-vf", vf,
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ])
        return

    if height > width and PORTRAIT_NORMALIZE_MODE in {"contain", "contain_blur", "fit", "fit_blur"}:
        bg_blur = "boxblur=24:2" if PORTRAIT_NORMALIZE_MODE in {"contain_blur", "fit_blur"} else "null"
        filter_complex = (
            f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},{bg_blur},"
            f"eq=brightness=-0.05:saturation=0.82[bg];"
            f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"setsar=1,fps={fps}[fg];"
            f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1"
        )
        _run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(input_path),
            "-t", str(max(0.1, duration)),
            "-filter_complex", filter_complex,
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ])
        return

    _run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(input_path),
        "-t", str(max(0.1, duration)),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}",
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ])


def _extract_fallback_frame(input_path: Path, output_path: Path, duration: float) -> None:
    seek_seconds = max(0.0, min(max(duration, 0.1) * 0.5, 10.0))
    _run([
        "ffmpeg", "-y",
        "-ss", f"{seek_seconds:.3f}",
        "-i", str(input_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ])


def _run_command_provider(source: Path, audio: Path, output: Path, width: int, height: int, fps: int, duration: float) -> None:
    if not COMMAND_TEMPLATE:
        raise HTTPException(
            status_code=503,
            detail=(
                "LIPSYNC_COMMAND_TEMPLATE is not configured. "
                "Set it to a Wav2Lip/SadTalker/MuseTalk command that writes {output}."
            ),
        )
    values = {
        "source": str(source),
        "audio": str(audio),
        "output": str(output),
        "width": str(width),
        "height": str(height),
        "fps": str(fps),
        "duration": str(duration),
    }
    command = COMMAND_TEMPLATE.format(**values)
    _run(shlex.split(command))


def _run_wav2lip_provider(source: Path, audio: Path, output: Path, fps: int) -> None:
    checkpoint = Path(WAV2LIP_CHECKPOINT) if WAV2LIP_CHECKPOINT else WAV2LIP_DIR / "checkpoints" / "wav2lip_gan.pth"
    inference = WAV2LIP_DIR / "inference.py"
    if not inference.exists() or not checkpoint.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Wav2Lip is not installed or checkpoint is missing: {inference}, {checkpoint}",
        )
    _run([
        "python", str(inference),
        "--checkpoint_path", str(checkpoint),
        "--face", str(source),
        "--audio", str(audio),
        "--outfile", str(output),
        "--fps", str(fps),
        "--face_det_batch_size", WAV2LIP_FACE_DET_BATCH_SIZE,
        "--wav2lip_batch_size", WAV2LIP_BATCH_SIZE,
    ], cwd=WAV2LIP_DIR)


def _ensure_mp4(video: Path, output: Path, width: int, height: int, fps: int, duration: float) -> None:
    if not video.exists() or video.stat().st_size <= 0:
        raise HTTPException(status_code=500, detail="lip-sync provider did not produce a video")
    normalized = output.with_name("normalized.mp4")
    _normalize_video(video, normalized, width, height, fps, duration)
    shutil.move(str(normalized), output)


@app.get("/health")
def health():
    return {
        "ok": True,
        "version": APP_VERSION,
        "provider": PROVIDER,
        "command_configured": bool(COMMAND_TEMPLATE),
        "wav2lip_dir_exists": WAV2LIP_DIR.exists(),
        "wav2lip_checkpoint": WAV2LIP_CHECKPOINT or str(WAV2LIP_DIR / "checkpoints" / "wav2lip_gan.pth"),
        "wav2lip_face_det_batch_size": WAV2LIP_FACE_DET_BATCH_SIZE,
        "wav2lip_batch_size": WAV2LIP_BATCH_SIZE,
    }


@app.post("/generate")
def generate(
    source: UploadFile = File(...),
    audio: UploadFile = File(...),
    speaker: str = Form("AnalystK"),
    width: int = Form(1080),
    height: int = Form(1920),
    fps: int = Form(30),
    duration: float = Form(5.0),
    mode: str = Form("high_precision"),
):
    job_id = f"{int(time.time())}_{uuid.uuid4().hex[:10]}"
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    source_path = job_dir / f"source{_safe_suffix(source.filename, '.mp4')}"
    audio_path = job_dir / f"audio{_safe_suffix(audio.filename, '.wav')}"
    provider_output = job_dir / "provider_output.mp4"
    output_path = job_dir / OUTPUT_NAME
    _copy_upload(source, source_path)
    _copy_upload(audio, audio_path)

    print(
        f"[lipsync-service] job={job_id} speaker={speaker} mode={mode} "
        f"provider={PROVIDER} size={width}x{height}@{fps} duration={duration}",
        flush=True,
    )

    try:
        if PROVIDER == "wav2lip":
            try:
                _run_wav2lip_provider(source_path, audio_path, provider_output, fps)
            except subprocess.CalledProcessError:
                if source_path.suffix.lower() not in {".mp4", ".mov", ".mkv"}:
                    raise
                fallback_frame = job_dir / "source_fallback.jpg"
                print("[lipsync-service] video source failed; retrying with a static fallback frame", flush=True)
                _extract_fallback_frame(source_path, fallback_frame, duration)
                _run_wav2lip_provider(fallback_frame, audio_path, provider_output, fps)
        elif PROVIDER in {"command", "sadtalker", "musetalk"}:
            _run_command_provider(source_path, audio_path, provider_output, width, height, fps, duration)
        else:
            raise HTTPException(status_code=400, detail=f"unsupported provider: {PROVIDER}")
        _ensure_mp4(provider_output, output_path, width, height, fps, duration)
    except HTTPException:
        raise
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"lip-sync provider timeout: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=502, detail=f"lip-sync provider failed: {exc}") from exc

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"lipsync_{speaker}_{job_id}.mp4",
    )
