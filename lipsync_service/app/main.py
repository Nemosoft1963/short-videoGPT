import os
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
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


def _run_wav2lip_provider(source: Path, audio: Path, output: Path, fps: int, face_box: str = "") -> None:
    checkpoint = Path(WAV2LIP_CHECKPOINT) if WAV2LIP_CHECKPOINT else WAV2LIP_DIR / "checkpoints" / "wav2lip_gan.pth"
    inference = WAV2LIP_DIR / "inference.py"
    if not inference.exists() or not checkpoint.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Wav2Lip is not installed or checkpoint is missing: {inference}, {checkpoint}",
        )
    command = [
        "python", str(inference),
        "--checkpoint_path", str(checkpoint),
        "--face", str(source),
        "--audio", str(audio),
        "--outfile", str(output),
        "--fps", str(fps),
        "--face_det_batch_size", WAV2LIP_FACE_DET_BATCH_SIZE,
        "--wav2lip_batch_size", WAV2LIP_BATCH_SIZE,
    ]
    if face_box:
        try:
            box = [int(value.strip()) for value in face_box.split(",")]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="face_box must contain four integers") from exc
        if len(box) != 4 or min(box) < 0 or box[0] >= box[1] or box[2] >= box[3]:
            raise HTTPException(status_code=400, detail="face_box must be y1,y2,x1,x2")
        command.extend(["--box", *(str(value) for value in box)])
    _run(command, cwd=WAV2LIP_DIR)


def _blend_mouth_only(source: Path, synced: Path, output: Path, mouth_box: str) -> None:
    try:
        x1, y1, x2, y2 = [int(value.strip()) for value in mouth_box.split(",")]
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="mouth_box must be x1,y1,x2,y2") from exc
    original = cv2.VideoCapture(str(source))
    generated = cv2.VideoCapture(str(synced))
    process = None
    try:
        width = int(generated.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(generated.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = generated.get(cv2.CAP_PROP_FPS) or original.get(cv2.CAP_PROP_FPS) or 30
        if not original.isOpened() or not generated.isOpened() or (width, height) != (
            int(original.get(cv2.CAP_PROP_FRAME_WIDTH)), int(original.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ):
            raise HTTPException(status_code=422, detail="mouth-only blend requires same-size source and generated videos")
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise HTTPException(status_code=400, detail="mouth_box is outside the video frame")

        mask = np.zeros((height, width), dtype=np.float32)
        center = ((x1 + x2) // 2, (y1 + y2) // 2)
        axes = (max(1, (x2 - x1) // 2), max(1, (y2 - y1) // 2))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 1, -1)
        feather = max(4, min(axes) * 0.22)
        mask = cv2.GaussianBlur(mask, (0, 0), feather)[:, :, None]

        process = subprocess.Popen([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "bgr24",
            "-video_size", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(output),
        ], stdin=subprocess.PIPE)
        frame_count = 0
        while True:
            has_generated, generated_frame = generated.read()
            if not has_generated:
                break
            has_original, original_frame = original.read()
            if not has_original:
                original.set(cv2.CAP_PROP_POS_FRAMES, 0)
                has_original, original_frame = original.read()
            if not has_original:
                raise HTTPException(status_code=422, detail="source video has no readable frames")
            blended = original_frame.astype(np.float32) * (1 - mask) + generated_frame.astype(np.float32) * mask
            process.stdin.write(np.clip(blended, 0, 255).astype(np.uint8).tobytes())
            frame_count += 1
        process.stdin.close()
        if frame_count == 0 or process.wait(timeout=REQUEST_TIMEOUT_SECONDS) != 0:
            raise HTTPException(status_code=502, detail="mouth-only blend failed")
    finally:
        original.release()
        generated.release()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()


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
    face_box: str = Form(""),
    mouth_box: str = Form(""),
    allow_static_fallback: bool = Form(True),
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
                _run_wav2lip_provider(source_path, audio_path, provider_output, fps, face_box)
            except subprocess.CalledProcessError:
                if not allow_static_fallback or source_path.suffix.lower() not in {".mp4", ".mov", ".mkv"}:
                    raise
                fallback_frame = job_dir / "source_fallback.jpg"
                print("[lipsync-service] video source failed; retrying with a static fallback frame", flush=True)
                _extract_fallback_frame(source_path, fallback_frame, duration)
                _run_wav2lip_provider(fallback_frame, audio_path, provider_output, fps, face_box)
        elif PROVIDER in {"command", "sadtalker", "musetalk"}:
            _run_command_provider(source_path, audio_path, provider_output, width, height, fps, duration)
        else:
            raise HTTPException(status_code=400, detail=f"unsupported provider: {PROVIDER}")
        if mouth_box:
            if source_path.suffix.lower() not in {".mp4", ".mov", ".mkv"}:
                raise HTTPException(status_code=400, detail="mouth-only blend requires a video source")
            blended_output = job_dir / "mouth_only.mp4"
            _blend_mouth_only(source_path, provider_output, blended_output, mouth_box)
            provider_output = blended_output
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
