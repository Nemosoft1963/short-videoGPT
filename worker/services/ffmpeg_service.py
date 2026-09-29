import os
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Dict

BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.12"))
FONT_FILE = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
NARRATION_AUDIO_STABILIZE = os.getenv("NARRATION_AUDIO_STABILIZE", "true").lower() not in {"0", "false", "no", "off"}
NARRATION_LOUDNESS_I = float(os.getenv("NARRATION_LOUDNESS_I", "-8"))
NARRATION_LOUDNESS_LRA = float(os.getenv("NARRATION_LOUDNESS_LRA", "7"))
NARRATION_LOUDNESS_TP = float(os.getenv("NARRATION_LOUDNESS_TP", "-0.5"))
NARRATION_DYNAUDNORM_FRAME_MS = int(os.getenv("NARRATION_DYNAUDNORM_FRAME_MS", "350"))
NARRATION_DYNAUDNORM_GAIN = int(os.getenv("NARRATION_DYNAUDNORM_GAIN", "15"))
NARRATION_HIGHPASS_FREQUENCY = int(os.getenv("NARRATION_HIGHPASS_FREQUENCY", "90"))
NARRATION_LOW_MUD_GAIN = float(os.getenv("NARRATION_LOW_MUD_GAIN", "-1.5"))
NARRATION_PRESENCE_GAIN = float(os.getenv("NARRATION_PRESENCE_GAIN", "3.0"))
NARRATION_AIR_GAIN = float(os.getenv("NARRATION_AIR_GAIN", "1.5"))
NARRATION_PRE_FILTER_GAIN = float(os.getenv("NARRATION_PRE_FILTER_GAIN", "0.75"))
SCENE_AUDIO_NORMALIZE = os.getenv("SCENE_AUDIO_NORMALIZE", "true").lower() not in {"0", "false", "no", "off"}
ANALYSTK_DENOISE = os.getenv("ANALYSTK_DENOISE", "true").lower() not in {"0", "false", "no", "off"}
ANALYSTK_DENOISE_NOISE_FLOOR = float(os.getenv("ANALYSTK_DENOISE_NOISE_FLOOR", "-28"))
ANALYSTK_LOW_PASS_FREQUENCY = int(os.getenv("ANALYSTK_LOW_PASS_FREQUENCY", "9200"))


def run(cmd: List[str]):
    print("RUN:", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def probe_duration(path: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], check=True, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _has_audio_stream(path: Path) -> bool:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(path)
    ], check=True, capture_output=True, text=True)
    return bool(result.stdout.strip())


def create_mock_clip(out_path: Path, scene: Dict, width: int, height: int, fps: int):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = scene.get("duration", 6)
    title = f"SCENE {scene.get('scene_id', '')}"
    draw = (
        f"drawtext=fontfile='{FONT_FILE}':text='{title}':"
        f"fontsize=56:fontcolor=0xF4EFE6:x=(w-text_w)/2:y=h*0.42:"
        f"box=1:boxcolor=0x1A1714@0.65:boxborderw=28"
    )
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x1A1714:s={width}x{height}:r={fps}",
        "-f", "lavfi", "-i", f"sine=frequency=80:sample_rate=44100:duration={duration}",
        "-t", str(duration),
        "-vf", draw,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(out_path)
    ])


def normalize_clip(in_path: Path, out_path: Path, width: int, height: int, fps: int, duration: int):
    """クリップをリサイズ・クロップし、ちょうど duration 秒に整える。
    Runway など短いクリップは -stream_loop でループして尺を埋める。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}"
    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",   # 短いクリップをループして duration を満たす
        "-i", in_path,
        "-vf", vf,
        "-t", str(duration),
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path)
    ])


def overlay_lipsync_on_scene(
    base_path: Path,
    lipsync_path: Path,
    out_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_width = max(1, int(width * float(os.getenv("LIPSYNC_OVERLAY_WIDTH_RATIO", "0.94"))))
    margin_bottom = max(0, int(height * float(os.getenv("LIPSYNC_OVERLAY_BOTTOM_MARGIN_RATIO", "0.035"))))
    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps}[base];"
        f"[1:v]scale={overlay_width}:-2:force_original_aspect_ratio=decrease,"
        f"setsar=1,fps={fps}[talk];"
        f"[base][talk]overlay=x=(W-w)/2:y=H-h-{margin_bottom}:shortest=1"
    )
    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(base_path),
        "-stream_loop", "-1", "-i", str(lipsync_path),
        "-t", str(max(0.1, float(duration))),
        "-filter_complex", filter_complex,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ])


def overlay_lipsync_right_on_scene(
    base_path: Path,
    lipsync_path: Path,
    out_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
):
    """Standard landscape explainer: subtitles/content left, AnalystK right."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    talk_width = max(1, int(width * float(os.getenv("LIPSYNC_EXPLAIN_RIGHT_WIDTH_RATIO", "0.40"))))
    talk_height = max(1, int(height * float(os.getenv("LIPSYNC_EXPLAIN_RIGHT_HEIGHT_RATIO", "0.94"))))
    margin_right = max(0, int(width * float(os.getenv("LIPSYNC_EXPLAIN_RIGHT_MARGIN_RATIO", "0.015"))))
    margin_bottom = max(0, int(height * float(os.getenv("LIPSYNC_EXPLAIN_RIGHT_BOTTOM_MARGIN_RATIO", "0.02"))))
    left_panel_width = max(1, int(width * float(os.getenv("LIPSYNC_EXPLAIN_LEFT_PANEL_RATIO", "0.57"))))
    panel_alpha = min(1.0, max(0.0, float(os.getenv("LIPSYNC_EXPLAIN_LEFT_PANEL_ALPHA", "0.28"))))
    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},"
        f"drawbox=x=0:y=0:w={left_panel_width}:h=ih:color=black@{panel_alpha}:t=fill[base];"
        f"[1:v]scale={talk_width}:{talk_height}:force_original_aspect_ratio=increase,"
        f"crop={talk_width}:{talk_height},setsar=1,fps={fps}[talk];"
        f"[base][talk]overlay=x=W-w-{margin_right}:y=H-h-{margin_bottom}:shortest=1"
    )
    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(base_path),
        "-stream_loop", "-1", "-i", str(lipsync_path),
        "-t", str(max(0.1, float(duration))),
        "-filter_complex", filter_complex,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ])


def overlay_graphic_on_video(
    base_path: Path,
    graphic_path: Path,
    out_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
    opacity: float | None = None,
):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    alpha = float(opacity if opacity is not None else os.getenv("LIPSYNC_GRAPHIC_OVERLAY_OPACITY", "0.38"))
    alpha = min(1.0, max(0.0, alpha))
    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps}[base];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},format=rgba,"
        f"colorchannelmixer=aa={alpha}[fg];"
        f"[base][fg]overlay=x=0:y=0:shortest=1"
    )
    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(base_path),
        "-stream_loop", "-1", "-i", str(graphic_path),
        "-t", str(max(0.1, float(duration))),
        "-filter_complex", filter_complex,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ])


def hold_last_frame(in_path: Path, out_path: Path, hold_seconds: float) -> Path:
    """動画末尾の最終フレームを静止したまま指定秒数だけ延長する。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", str(in_path),
        "-vf", f"tpad=stop_mode=clone:stop_duration={max(0.0, float(hold_seconds))}",
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ])
    return out_path


def concat_videos(clips: List[Path], out_path: Path, width: int, height: int, fps: int, duration: int):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = out_path.parent / "concat_videos.txt"
    concat_file.write_text("\n".join([f"file '{p.as_posix()}'" for p in clips]), encoding="utf-8")
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_path)
    ])


def normalize_video_for_concat(in_path: Path, out_path: Path, width: int, height: int, fps: int) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}"
    duration = max(0.1, probe_duration(in_path))
    if _has_audio_stream(in_path):
        run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-vf", vf,
            "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(out_path)
        ])
    else:
        run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", vf,
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(out_path)
        ])
    return out_path


def concat_media_files(clips: List[Path], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = out_path.parent / "concat_media.txt"
    concat_file.write_text("\n".join([f"file '{p.as_posix()}'" for p in clips]), encoding="utf-8")
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c", "copy", "-movflags", "+faststart", str(out_path)
    ])
    return out_path


def force_media_duration(in_path: Path, out_path: Path, duration: float) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    target = max(0.1, float(duration))
    if _has_audio_stream(in_path):
        run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-vf", f"tpad=stop_mode=clone:stop_duration={target}",
            "-af", f"apad=pad_dur={target},atrim=0:{target}",
            "-t", f"{target:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(out_path)
        ])
    else:
        run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", f"tpad=stop_mode=clone:stop_duration={target}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{target:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(out_path)
        ])
    return out_path


def concat_audios(wavs: List[Path], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = out_path.parent / "concat_audio.txt"
    concat_file.write_text("\n".join([f"file '{p.as_posix()}'" for p in wavs]), encoding="utf-8")
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
        "-ar", "44100", "-ac", "2", str(out_path)
    ])


def stabilize_narration_audio(in_path: Path, out_path: Path) -> Path:
    """Apply fixed final narration EQ/loudness without long-form gain drift."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not NARRATION_AUDIO_STABILIZE:
        run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-ar", "44100", "-ac", "2", str(out_path)
        ])
        return out_path

    filter_chain = (
        f"loudnorm=I={NARRATION_LOUDNESS_I}:LRA={NARRATION_LOUDNESS_LRA}:TP={NARRATION_LOUDNESS_TP}:"
        "linear=true,"
        "alimiter=limit=0.98"
    )
    run([
        "ffmpeg", "-y", "-i", str(in_path),
        "-af", filter_chain,
        "-ar", "44100", "-ac", "2", str(out_path)
    ])
    return out_path


def normalize_scene_audio(in_path: Path, out_path: Path) -> Path:
    """Normalize each scene before concat so long videos do not ramp up near the end."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not SCENE_AUDIO_NORMALIZE:
        run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-ar", "44100", "-ac", "2", str(out_path)
        ])
        return out_path

    filter_chain = (
        f"volume={NARRATION_PRE_FILTER_GAIN},"
        f"highpass=f={NARRATION_HIGHPASS_FREQUENCY},"
        f"equalizer=f=260:t=q:w=1.1:g={NARRATION_LOW_MUD_GAIN},"
        f"equalizer=f=3200:t=q:w=1.0:g={NARRATION_PRESENCE_GAIN},"
        f"equalizer=f=6500:t=q:w=1.0:g={NARRATION_AIR_GAIN},"
        f"loudnorm=I={NARRATION_LOUDNESS_I}:LRA={NARRATION_LOUDNESS_LRA}:TP={NARRATION_LOUDNESS_TP}:"
        "linear=true,"
        "alimiter=limit=0.98"
    )
    run([
        "ffmpeg", "-y", "-i", str(in_path),
        "-af", filter_chain,
        "-ar", "44100", "-ac", "2", str(out_path)
    ])
    return out_path


def clean_analystk_audio(in_path: Path, out_path: Path) -> Path:
    """Reduce Qwen/Wav2Lip-adjacent hiss and brittle highs for AnalystK only."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not ANALYSTK_DENOISE:
        run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-ar", "44100", "-ac", "2", str(out_path)
        ])
        return out_path

    filter_chain = (
        f"afftdn=nf={ANALYSTK_DENOISE_NOISE_FLOOR}:tn=1,"
        f"lowpass=f={ANALYSTK_LOW_PASS_FREQUENCY},"
        "deesser=i=0.35:m=0.45:f=0.55,"
        f"loudnorm=I={NARRATION_LOUDNESS_I}:LRA={NARRATION_LOUDNESS_LRA}:TP={NARRATION_LOUDNESS_TP}:"
        "linear=true,"
        "alimiter=limit=0.98"
    )
    run([
        "ffmpeg", "-y", "-i", str(in_path),
        "-af", filter_chain,
        "-ar", "44100", "-ac", "2", str(out_path)
    ])
    return out_path


def _atempo_filter(tempo: float) -> str:
    """FFmpeg atempoを安全な範囲へ分割します。"""
    tempo = max(0.5, min(4.0, float(tempo)))
    parts = []
    while tempo > 2.0:
        parts.append("atempo=2.0")
        tempo /= 2.0
    while tempo < 0.5:
        parts.append("atempo=0.5")
        tempo /= 0.5
    parts.append(f"atempo={tempo:.6f}")
    return ",".join(parts)


def fit_audio_to_duration(in_path: Path, out_path: Path, target_duration: float) -> Path:
    """音声を各シーン尺に合わせる。長い音声は速くし、短い音声は無音を足す。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    actual = max(0.01, probe_duration(in_path))
    target = max(0.10, float(target_duration))

    if abs(actual - target) < 0.08:
        run([
            "ffmpeg", "-y", "-i", in_path,
            "-af", f"apad=pad_dur=1,atrim=0:{target}",
            "-ar", "44100", "-ac", "2", str(out_path)
        ])
        return out_path

    if actual > target:
        tempo = actual / target
        run([
            "ffmpeg", "-y", "-i", in_path,
            "-filter:a", _atempo_filter(tempo),
            "-t", str(target),
            "-ar", "44100", "-ac", "2", str(out_path)
        ])
        return out_path

    run([
        "ffmpeg", "-y", "-i", in_path,
        "-af", f"apad=pad_dur={target - actual + 0.2},atrim=0:{target}",
        "-ar", "44100", "-ac", "2", str(out_path)
    ])
    return out_path


def mux_audio(video: Path, audio: Path, out_path: Path, duration: int):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", video, "-i", audio,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", str(duration),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(out_path)
    ])


def add_bgm(video_with_audio: Path, bgm: Path, out_path: Path, duration: int):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = f"[1:a]volume={BGM_VOLUME},aloop=loop=-1:size=2e+09[a2];[0:a][a2]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
    run([
        "ffmpeg", "-y", "-i", video_with_audio, "-i", bgm,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[a]",
        "-t", str(duration),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(out_path)
    ])


def burn_text_overlay(
    video: Path,
    text: str,
    out_path: Path,
    width: int = 1080,
    height: int = 1920,
    font_size: int = 56,
    y_start_pct: float = 38.0,
    placement: str = "center",
) -> Path:
    """映像シーンの上部に固定テキストを焼き込む。テキストは改行（\\n）で複数行可。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [l.strip() for l in text.replace("\\n", "\n").split("\n") if l.strip()]
    if not lines:
        return video

    def esc(s):
        return (
            s.replace("\\", r"\\")
            .replace("'", r"\'")
            .replace(":", r"\:")
            .replace("%", r"\%")
            .replace(",", r"\,")
        )

    filters = []
    def display_width(s: str) -> int:
        return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1 for ch in s)

    def wrap_line(line: str, max_units: int) -> List[str]:
        wrapped, current, units = [], "", 0
        for ch in line.strip():
            ch_units = 2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1
            if current and units + ch_units > max_units:
                wrapped.append(current.strip())
                current, units = ch, ch_units
            else:
                current += ch
                units += ch_units
        if current.strip():
            wrapped.append(current.strip())
        return wrapped

    if placement == "corner_note":
        is_portrait = height > width
        max_units = 27 if is_portrait else 36
        wrapped_lines: List[str] = []
        for raw_line in lines:
            wrapped_lines.extend(wrap_line(raw_line, max_units))
        max_visible_lines = 8 if is_portrait else 5
        lines = wrapped_lines[:max_visible_lines]

        max_line_units = max((display_width(line) for line in lines), default=max_units)
        note_font_size = max(
            26,
            min(
                font_size,
                int(width * (0.038 if is_portrait else 0.028)),
                int(width * 1.42 / max(16, max_line_units)),
            ),
        )
        y_start = int(height * (0.265 if is_portrait else 0.075))
        x_pos = int(width * 0.055)
        line_height = int(note_font_size * 1.45)
        max_width = int(width * (0.90 if is_portrait else 0.50))
        box_h = line_height * len(lines) + int(note_font_size * 0.9)
        filters.append(
            f"drawbox=x={x_pos - 18}:y={y_start - 18}:w={max_width}:h={box_h}:"
            f"color=0x141714@0.78:t=fill"
        )
        filters.append(
            f"drawbox=x={x_pos - 18}:y={y_start - 18}:w=5:h={box_h}:"
            f"color=0xB8341C@0.95:t=fill"
        )
        for i, line in enumerate(lines):
            y = y_start + i * line_height
            filters.append(
                f"drawtext=fontfile='{FONT_FILE}':text='{esc(line)}':"
                f"fontsize={note_font_size}:fontcolor=0xF4EFE6:"
                f"x={x_pos}:y={y}:"
                f"borderw=2:bordercolor=0x141714:box=0"
            )
    else:
        is_portrait = height > width
        max_units = 24 if is_portrait else 42
        wrapped_lines: List[str] = []
        for raw_line in lines:
            wrapped_lines.extend(wrap_line(raw_line, max_units))
        lines = wrapped_lines[:6 if is_portrait else 4]
        max_line_units = max((display_width(line) for line in lines), default=max_units)
        available_height = int(height * 0.34)
        font_size = max(
            28,
            min(
                font_size,
                int(width * 1.55 / max(12, max_line_units)),
                int(available_height / max(1, len(lines)) * 0.72),
            ),
        )
        y_start = int(height * y_start_pct / 100)
        line_height = int(font_size * 1.32)
        for i, line in enumerate(lines):
            y = y_start + i * line_height
            filters.append(
                f"drawtext=fontfile='{FONT_FILE}':text='{esc(line)}':"
                f"fontsize={font_size}:fontcolor=0xF4EFE6:"
                f"x=(w-text_w)/2:y={y}:"
                f"box=1:boxcolor=0x141714@0.75:boxborderw=18"
            )

    run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path)
    ])
    return out_path


def burn_head_title(
    video: Path,
    text: str,
    out_path: Path,
    width: int,
    height: int,
    duration: float = 3.0,
) -> Path:
    """完成動画の冒頭だけにヘッドタイトルを焼き込む。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    title = (text or "").replace("\\n", "\n").strip()
    if not title:
        return video

    def esc(s):
        return (
            s.replace("\\", r"\\")
            .replace("'", r"\'")
            .replace(":", r"\:")
            .replace("%", r"\%")
            .replace(",", r"\,")
        )

    def display_width(s: str) -> int:
        return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1 for ch in s)

    def wrap_line(line: str, max_units: int) -> List[str]:
        wrapped, current, units = [], "", 0
        for ch in line.strip():
            ch_units = 2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1
            if current and units + ch_units > max_units:
                wrapped.append(current.strip())
                current, units = ch, ch_units
            else:
                current += ch
                units += ch_units
        if current.strip():
            wrapped.append(current.strip())
        return wrapped

    max_units = 34 if width > height else 22
    lines: List[str] = []
    for raw_line in title.splitlines():
        lines.extend(wrap_line(raw_line, max_units))
    lines = lines[:3] or [title]
    max_line_units = max(display_width(line) for line in lines)
    font_size = max(38, min(82, int(width * 1.42 / max(16, max_line_units))))
    line_height = int(font_size * 1.28)
    padding_y = int(font_size * 0.55)
    box_y = int(height * 0.055)
    box_h = line_height * len(lines) + padding_y * 2
    y_start = box_y + padding_y
    alpha = f"if(lt(t,0.35),t/0.35,if(gt(t,{duration - 0.35}),({duration}-t)/0.35,1))"
    filters = [
        f"drawbox=x=0:y={box_y}:w=iw:h={box_h}:"
        f"color=0x141714@0.72:t=fill:enable='between(t,0,{duration})'"
    ]
    for index, line in enumerate(lines):
        y = y_start + index * line_height
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{esc(line)}':"
            f"fontsize={font_size}:fontcolor=0xF4EFE6:"
            f"x=(w-text_w)/2:y={y}:"
            f"borderw=3:bordercolor=0x141714:"
            f"enable='between(t,0,{duration})':"
            f"alpha='{alpha}'"
        )
    vf = ",".join(filters)

    run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out_path)
    ])
    return out_path


def extract_thumbnail(video: Path, out_path: Path, at_seconds: float = 0.0) -> Path:
    """動画からサムネイルJPEGを切り出す。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    at_seconds = max(0.0, float(at_seconds or 0.0))
    run([
        "ffmpeg", "-y",
        "-ss", f"{at_seconds:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_path)
    ])
    return out_path


def create_final_call_clip(
    text: str,
    audio: Path,
    out_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
) -> Path:
    """最終コール用の文字表示付き動画を作る。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = (text or "").replace("\\n", "\n").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()] or [text]

    def esc(s):
        return s.replace("'", r"\'").replace(":", r"\:").replace("%", r"\%")

    font_size = max(52, min(110, int(width / max(9, max(len(x) for x in lines))) * 2))
    line_height = int(font_size * 1.35)
    total_h = line_height * len(lines)
    y_start = int((height - total_h) / 2)
    filters = [
        f"geq=lum='clip(34+90*sin(2*PI*(X/{width}+T/8))*cos(2*PI*(Y/{height}+T/12)),5,130)':cb='118':cr='132'",
        "vignette=angle=PI/4",
        f"drawbox=x={int(width*0.08)}:y={int(height*0.30)}:w={int(width*0.84)}:h={int(height*0.40)}:color=0x141714@0.70:t=fill",
        f"drawbox=x={int(width*0.08)}:y={int(height*0.30)}:w={int(width*0.84)}:h={int(height*0.40)}:color=0xB8341C@0.85:t=4",
    ]
    for index, line in enumerate(lines):
        y = y_start + index * line_height
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{esc(line)}':"
            f"fontsize={font_size}:fontcolor=0xF4EFE6:"
            f"x=(w-text_w)/2:y={y}:"
            f"borderw=4:bordercolor=0x141714:"
            f"alpha='if(lt(t,0.35),t/0.35,if(gt(t,{duration - 0.35}),({duration}-t)/0.35,1))'"
        )

    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x1A1714:s={width}x{height}:r={fps}",
        "-i", str(audio),
        "-t", f"{duration:.3f}",
        "-vf", ",".join(filters),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(out_path)
    ])
    return out_path


def burn_ass_subtitles(video: Path, ass_path: Path, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"ass={ass_path.as_posix()}"
    run([
        "ffmpeg", "-y", "-i", video,
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out_path)
    ])
