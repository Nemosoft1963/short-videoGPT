import os
import json
import hashlib
import re
import shutil
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.scene_planner import build_scenes
from services.tts_factory import get_tts_client
from services.voice_profiles import get_voice_profile
from services.subtitle_service import write_ass_subtitles, write_srt_subtitles
from services.ffmpeg_service import (
    create_mock_clip,
    normalize_clip,
    hold_last_frame,
    concat_videos,
    concat_audios,
    mux_audio,
    burn_ass_subtitles,
    add_bgm,
    fit_audio_to_duration,
    normalize_scene_audio,
    clean_analystk_audio,
    stabilize_narration_audio,
    probe_duration,
    burn_text_overlay,
    burn_head_title,
    overlay_lipsync_on_scene,
    overlay_lipsync_right_on_scene,
    overlay_graphic_on_video,
    extract_thumbnail,
    create_final_call_clip,
    normalize_video_for_concat,
    concat_media_files,
    force_media_duration,
)
from services.ffmpeg_graphic_service import create_graphic_clip, is_graphic_mode
from services.ffmpeg_insert_service import apply_insert_overlay
from services.ffmpeg_logo_bgm import overlay_logo, add_bgm_auto, add_scene_bgms
from services.ffmpeg_flash_service import create_flash_sound, ensure_flash_visual_clip
from services.lipsync_client import generate_lipsync_clip, lipsync_enabled
from services.voice_profiles import normalize_speaker

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
VIDEO_ENGINE = os.getenv("VIDEO_ENGINE", "mock").lower()
REMOTE_VIDEO_MODELS = {"runway", "luma", "veo_lite", "veo-lite", "google_veo_lite", "minimax", "hailuo", "minimax_hailuo"}
TTS_ENGINE = os.getenv("TTS_ENGINE", "stylebertvits2").lower()
DEFAULT_WIDTH = int(os.getenv("DEFAULT_WIDTH", "1080"))
DEFAULT_HEIGHT = int(os.getenv("DEFAULT_HEIGHT", "1920"))
DEFAULT_FPS = int(os.getenv("DEFAULT_FPS", "30"))
DEFAULT_TTS_SPEAKER_ID = int(os.getenv("STYLEBERTVITS2_SPEAKER_ID", "0"))
DEFAULT_VOICE_SPEED = float(os.getenv("DEFAULT_VOICE_SPEED", "1.08"))
SHORT_VERTICAL_MIN_VOICE_SPEED = float(os.getenv("SHORT_VERTICAL_MIN_VOICE_SPEED", "1.22"))
AUDIO_MAX_TEMPO_COMPRESSION = float(os.getenv("AUDIO_MAX_TEMPO_COMPRESSION", "1.10"))
AUDIO_MAX_TAIL_PAD_SECONDS = float(os.getenv("AUDIO_MAX_TAIL_PAD_SECONDS", "0.80"))
AUDIO_MIN_SCENE_DURATION = float(os.getenv("AUDIO_MIN_SCENE_DURATION", "2.60"))
SUBTITLE_READ_CHARS_PER_SECOND = float(os.getenv("SUBTITLE_READ_CHARS_PER_SECOND", "8.0"))
FIXED_SHORT_REINFORCE_ENABLED = os.getenv("FIXED_SHORT_REINFORCE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
FIXED_SHORT_REINFORCE_GAP_SECONDS = float(os.getenv("FIXED_SHORT_REINFORCE_GAP_SECONDS", "4.5"))
FIXED_SHORT_REINFORCE_MAX_REPEATS = int(os.getenv("FIXED_SHORT_REINFORCE_MAX_REPEATS", "1"))
FIXED_SHORT_REINFORCE_SPEED_SCALE = float(os.getenv("FIXED_SHORT_REINFORCE_SPEED_SCALE", "0.92"))
DEFAULT_SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "72"))
DIALOGUE_PAUSE_SECONDS = float(os.getenv("DIALOGUE_PAUSE_SECONDS", "0.08"))
TTS_PARALLEL_WORKERS = int(os.getenv("TTS_PARALLEL_WORKERS", "4"))
FINAL_CALL_DIR = STORAGE_DIR / "assets" / "final_calls"
LONG_FORM_CHAPTER_MIN_DURATION = float(os.getenv("LONG_FORM_CHAPTER_MIN_DURATION", "180"))
CHAPTER_TARGET_GAP_SECONDS = float(os.getenv("CHAPTER_TARGET_GAP_SECONDS", "60"))
CHAPTER_MIN_GAP_SECONDS = float(os.getenv("CHAPTER_MIN_GAP_SECONDS", "30"))
CHAPTER_MAX_COUNT = int(os.getenv("CHAPTER_MAX_COUNT", "8"))
FINAL_SCENE_HOLD_SECONDS = float(os.getenv("FINAL_SCENE_HOLD_SECONDS", "2.5"))
FIXED_SHORT_FINAL_SCENE_HOLD_SECONDS = float(os.getenv("FIXED_SHORT_FINAL_SCENE_HOLD_SECONDS", "1.0"))
FIXED_SHORT_TARGET_DURATIONS = {
    "fixed_44": 44.0,
    "fixed_57": 57.0,
}


def _is_qwen3_engine(engine: str | None) -> bool:
    return (engine or "").lower().replace("-fallback", "").replace("_", "-") in {"qwen3tts", "qwen3-tts", "qwen"}


def _readable_text_duration(text: str | None) -> float:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return 0.0
    cps = max(1.0, SUBTITLE_READ_CHARS_PER_SECOND)
    return len(compact) / cps + 0.6


def _compact_emphasis_phrase(scene: dict) -> str:
    candidates = [
        scene.get("subtitle"),
        scene.get("overlay_text"),
        scene.get("narration"),
    ]
    for turn in scene.get("dialogue", []) or []:
        if turn.get("text"):
            candidates.append(turn.get("text"))
    for raw in candidates:
        text = re.sub(r"\s+", "", raw or "")
        text = re.sub(r"^(字幕|テキスト|重要|ポイント)[:：]", "", text)
        if not text:
            continue
        parts = [p for p in re.split(r"[。！？!?]", text) if p]
        phrase = parts[-1] if parts else text
        if len(phrase) < 8 and parts:
            phrase = parts[0]
        phrase = re.sub(r"^(重要なのは|見るべきは|ポイントは|つまり|結論は)[、:：]?", "", phrase)
        if len(phrase) > 34:
            phrase = phrase[:34]
        return phrase.strip("、。！？!? ")
    return ""


def _is_silent_scene(scene: dict) -> bool:
    if (scene.get("narration") or "").strip() or (scene.get("subtitle") or "").strip():
        return False
    return not any((turn.get("text") or "").strip() for turn in scene.get("dialogue") or [])


def _should_reinforce_fixed_short_scene(project: dict, scene: dict, raw_duration: float, target_duration: float) -> bool:
    if not FIXED_SHORT_REINFORCE_ENABLED:
        return False
    if project.get("format") != "short_vertical":
        return False
    if project.get("short_timing_mode", "fixed_57") not in FIXED_SHORT_TARGET_DURATIONS:
        return False
    if scene.get("is_flash") or _is_silent_scene(scene):
        return False
    return (target_duration - raw_duration) >= FIXED_SHORT_REINFORCE_GAP_SECONDS


def _is_analystk_scene(scene: dict) -> bool:
    return _analystk_character_speaker(scene) is not None


def _analystk_character_speaker(scene: dict) -> str | None:
    speakers = []
    if scene.get("speaker"):
        speakers.append(scene.get("speaker"))
    speakers.extend(turn.get("speaker") for turn in scene.get("dialogue", []) if turn.get("speaker"))
    for speaker in speakers:
        normalized = normalize_speaker(speaker)
        if normalized in {"AnalystK", "Major"}:
            return normalized
    return None


def _is_analystk_character_scene(scene: dict) -> bool:
    return _analystk_character_speaker(scene) is not None


def _apply_analystk_lipsync(
    *,
    project_id: str,
    project: dict,
    scenes: list[dict],
    raw_clips: list[Path],
    scene_wavs: list[Path],
    clip_dir: Path,
    output_width: int,
    output_height: int,
    output_fps: int,
) -> None:
    if not lipsync_enabled():
        return
    lipsync_source_mode = str(project.get("analystk_lipsync_source_mode") or os.getenv("LIPSYNC_ANALYSTK_SOURCE_MODE", "image"))
    lipsync_source_set = str(project.get("analystk_lipsync_source_set") or os.getenv("LIPSYNC_ANALYSTK_SOURCE_SET", "anime"))
    lipsync_display_mode = str(project.get("analystk_lipsync_display_mode") or os.getenv("LIPSYNC_ANALYSTK_DISPLAY_MODE", "bottom"))
    if lipsync_display_mode not in {"bottom", "full", "explain_right"}:
        lipsync_display_mode = "bottom"
    if lipsync_display_mode == "explain_right" and project.get("format") != "standard_landscape":
        lipsync_display_mode = "bottom"
    for index, scene in enumerate(scenes):
        character_speaker = _analystk_character_speaker(scene)
        if not character_speaker:
            continue
        if index >= len(raw_clips) or index >= len(scene_wavs):
            continue
        scene_no = index + 1
        source_clip = raw_clips[index]
        audio_path = scene_wavs[index]
        scene_source_mode = str(scene.get("lipsync_source_mode") or lipsync_source_mode)
        scene_source_set = str(scene.get("lipsync_source_set") or lipsync_source_set)
        scene_display_mode = str(scene.get("lipsync_display_mode") or lipsync_display_mode)
        if character_speaker == "Major":
            scene_source_mode = "video"
        if scene_display_mode not in {"bottom", "full", "explain_right"}:
            scene_display_mode = lipsync_display_mode
        if scene_display_mode == "explain_right" and project.get("format") != "standard_landscape":
            scene_display_mode = "bottom"
        lipsync_raw = clip_dir / f"scene_{scene_no:02d}_lipsync_raw.mp4"
        lipsync_norm = clip_dir / f"scene_{scene_no:02d}_lipsync.mp4"
        lipsync_overlay = clip_dir / f"scene_{scene_no:02d}_lipsync_overlay.mp4"
        lipsync_graphic_overlay = clip_dir / f"scene_{scene_no:02d}_lipsync_graphic_overlay.mp4"
        scene_duration = float(scene.get("duration") or 0)
        lipsync_width = output_width
        lipsync_height = output_height
        if scene_display_mode == "bottom" and output_height > output_width:
            lipsync_height = max(360, int(output_width * 9 / 16))
        elif scene_display_mode == "explain_right":
            lipsync_width = max(640, int(output_width * 0.40))
            lipsync_height = output_height
        character_name = "少佐" if character_speaker == "Major" else "分析官K"
        try:
            set_status(project_id, "lipsync", 66, f"シーン{scene_no}: {character_name}リップシンク生成中")
            created = generate_lipsync_clip(
                audio_path=audio_path,
                fallback_source_path=source_clip,
                out_path=lipsync_raw,
                width=lipsync_width,
                height=lipsync_height,
                fps=output_fps,
                duration=scene_duration,
                speaker=character_speaker,
                source_mode=scene_source_mode,
                source_set=scene_source_set,
            )
            if not created:
                if character_speaker == "Major":
                    raise RuntimeError("Major lipsync was required, but no lipsync clip was created")
                continue
            normalize_clip(
                lipsync_raw,
                lipsync_norm,
                lipsync_width,
                lipsync_height,
                output_fps,
                scene_duration,
            )
            if scene_display_mode == "full":
                final_lipsync_clip = lipsync_norm
                graphic_overlay_prompt = (scene.get("graphic_overlay_prompt") or "").strip()
                if graphic_overlay_prompt:
                    graphic_raw = clip_dir / f"scene_{scene_no:02d}_graphic_overlay_raw.mp4"
                    graphic_norm = clip_dir / f"scene_{scene_no:02d}_graphic_overlay.mp4"
                    overlay_scene = dict(scene)
                    overlay_scene["visual_prompt"] = graphic_overlay_prompt
                    set_status(project_id, "lipsync", 68, f"scene {scene_no}: graphic overlay compositing")
                    create_graphic_clip(graphic_raw, overlay_scene, output_width, output_height, output_fps)
                    normalize_clip(graphic_raw, graphic_norm, output_width, output_height, output_fps, scene_duration)
                    overlay_graphic_on_video(
                        lipsync_norm,
                        graphic_norm,
                        lipsync_graphic_overlay,
                        output_width,
                        output_height,
                        output_fps,
                        scene_duration,
                    )
                    final_lipsync_clip = lipsync_graphic_overlay
                raw_clips[index] = final_lipsync_clip
                print(f"[lipsync] scene {scene_no} replaced with full-frame high precision {character_speaker} clip")
            elif scene_display_mode == "explain_right":
                overlay_lipsync_right_on_scene(
                    source_clip,
                    lipsync_norm,
                    lipsync_overlay,
                    output_width,
                    output_height,
                    output_fps,
                    scene_duration,
                )
                raw_clips[index] = lipsync_overlay
                print(f"[lipsync] scene {scene_no} overlaid as right-side {character_speaker} explainer")
            else:
                overlay_lipsync_on_scene(
                    source_clip,
                    lipsync_norm,
                    lipsync_overlay,
                    output_width,
                    output_height,
                    output_fps,
                    scene_duration,
                )
                raw_clips[index] = lipsync_overlay
                print(f"[lipsync] scene {scene_no} overlaid with high precision {character_speaker} clip")
        except Exception as exc:
            if character_speaker == "Major":
                raise RuntimeError(f"Major lipsync failed in scene {scene_no}: {type(exc).__name__}: {exc}") from exc
            print(f"[lipsync] scene {scene_no} failed, keeping original clip: {type(exc).__name__}: {exc}")


def _final_scene_hold_seconds(project: dict) -> float:
    if project.get("format") == "short_vertical" and project.get("short_timing_mode", "fixed_57") in FIXED_SHORT_TARGET_DURATIONS:
        return FIXED_SHORT_FINAL_SCENE_HOLD_SECONDS
    return FINAL_SCENE_HOLD_SECONDS


def _is_silent_ending_scene(scene: dict) -> bool:
    if (scene.get("narration") or "").strip():
        return False
    if (scene.get("subtitle") or "").strip():
        return False
    if any((turn.get("text") or "").strip() for turn in scene.get("dialogue") or []):
        return False
    visual = (scene.get("visual_prompt") or "").lower()
    return "[graphic" in visual or bool((scene.get("overlay_text") or "").strip())


def _scene_final_hold_seconds(project: dict, scene: dict, is_last_scene: bool) -> float:
    if not is_last_scene:
        return 0.0
    hold = _final_scene_hold_seconds(project)
    if project.get("format") == "short_vertical" and _is_silent_ending_scene(scene):
        return 0.0
    return hold


def _output_settings(project: dict) -> tuple[int, int, int, str]:
    if project.get("format") == "standard_landscape":
        return 1920, 1080, DEFAULT_FPS, "1280:720"
    return DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS, "720:1280"


SCENE_CLIP_CACHE_DIR = STORAGE_DIR / "assets" / "scene_clip_cache"
SCENE_CLIP_CACHE_PRIOR_PROJECT_COPY = os.getenv("SCENE_CLIP_CACHE_PRIOR_PROJECT_COPY", "false").lower() in {"1", "true", "yes", "on"}


def _scene_clip_cache_payload(
    project: dict,
    scene: dict,
    selected_model: str,
    width: int,
    height: int,
    fps: int,
    background_video_path: Path | None,
) -> dict:
    return {
        "renderer_version": 5,
        "visual_prompt": (scene.get("visual_prompt") or "").strip(),
        "negative_prompt": (scene.get("negative_prompt") or "").strip(),
        "narration": (scene.get("narration") or "").strip(),
        "subtitle": (scene.get("subtitle") or "").strip(),
        "overlay_text": (scene.get("overlay_text") or "").strip(),
        "insert_video_id": scene.get("insert_video_id") or "",
        "insert_layer": scene.get("insert_layer") or "",
        "motoko_lipsync": bool(scene.get("motoko_lipsync")),
        "lipsync_display_mode": scene.get("lipsync_display_mode") or "",
        "lipsync_source_set": scene.get("lipsync_source_set") or "",
        "lipsync_source_mode": scene.get("lipsync_source_mode") or "",
        "graphic_overlay_prompt": (scene.get("graphic_overlay_prompt") or "").strip(),
        "duration": round(float(scene.get("duration") or 0), 3),
        "is_flash": bool(scene.get("is_flash")),
        "flash_word": scene.get("flash_word"),
        "flash_prompt": scene.get("flash_prompt"),
        "model": selected_model,
        "format": project.get("format"),
        "width": width,
        "height": height,
        "fps": fps,
        "background_video": str(background_video_path) if background_video_path else "",
    }


def _scene_clip_cache_path(payload: dict) -> Path:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return SCENE_CLIP_CACHE_DIR / f"{digest}.mp4"


def _copy_if_valid(src: Path, dst: Path) -> bool:
    if not src.exists() or src.stat().st_size <= 0:
        return False
    if not _is_valid_video_file(src):
        print(f"[scene-cache] invalid video skipped: {src}", flush=True)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _is_valid_video_file(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        return result.returncode == 0 and "video" in result.stdout
    except Exception:
        return False


def _load_scene_clip_cache(payload: dict, out_path: Path) -> bool:
    cached = _scene_clip_cache_path(payload)
    if _copy_if_valid(cached, out_path):
        print(f"[scene-cache] hit: {cached.name}", flush=True)
        return True
    if cached.exists() and cached.stat().st_size > 0:
        try:
            cached.unlink()
            meta = cached.with_suffix(".json")
            if meta.exists():
                meta.unlink()
            print(f"[scene-cache] removed invalid cache: {cached.name}", flush=True)
        except OSError:
            pass
    return False


def _save_scene_clip_cache(payload: dict, src_path: Path) -> None:
    if not _is_valid_video_file(src_path):
        print(f"[scene-cache] skip saving invalid video: {src_path}", flush=True)
        return
    SCENE_CLIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = _scene_clip_cache_path(payload)
    shutil.copy2(src_path, cached)
    cached.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[scene-cache] saved: {cached.name}", flush=True)


def _load_prior_project_scene_clip(current_project_id: str, payload: dict, out_path: Path) -> bool:
    if not SCENE_CLIP_CACHE_PRIOR_PROJECT_COPY:
        return False
    projects_dir = STORAGE_DIR / "projects"
    if not projects_dir.exists():
        return False
    for pdir in sorted(projects_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if pdir.name == current_project_id or not pdir.is_dir():
            continue
        scenes_path = pdir / "scenes.json"
        if not scenes_path.exists():
            continue
        try:
            scenes_data = read_json(scenes_path)
        except Exception:
            continue
        prior_scenes = scenes_data.get("scenes", []) if isinstance(scenes_data, dict) else []
        for idx, prior_scene in enumerate(prior_scenes, start=1):
            prior_payload = _scene_clip_cache_payload(
                {
                    "format": payload.get("format"),
                },
                prior_scene,
                payload.get("model", ""),
                int(payload.get("width") or 0),
                int(payload.get("height") or 0),
                int(payload.get("fps") or 0),
                Path(payload["background_video"]) if payload.get("background_video") else None,
            )
            if prior_payload != payload:
                continue
            if round(float(prior_scene.get("duration") or 0), 3) != payload["duration"]:
                continue
            if (prior_scene.get("visual_prompt") or "").strip() != payload["visual_prompt"]:
                continue
            if (prior_scene.get("negative_prompt") or "").strip() != payload["negative_prompt"]:
                continue
            candidate = pdir / "clips" / f"scene_{idx:02d}_raw.mp4"
            if _copy_if_valid(candidate, out_path):
                print(f"[scene-cache] copied from prior project {pdir.name}/scene_{idx:02d}", flush=True)
                _save_scene_clip_cache(payload, out_path)
                return True
    return False


def project_dir(project_id: str) -> Path:
    return STORAGE_DIR / "projects" / project_id


class VideoGenerationCancelled(Exception):
    pass


def check_cancel(project_id: str):
    if (project_dir(project_id) / "cancel.flag").exists():
        raise VideoGenerationCancelled("ユーザーにより中断されました")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_status(project_id: str, status: str, progress: int, message: str, **extra):
    data = {
        "project_id": project_id,
        "status": status,
        "progress": progress,
        "message": message,
    }
    data.update(extra)
    write_json(project_dir(project_id) / "status.json", data)


def _format_chapter_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _clean_chapter_title(text: str, fallback: str) -> str:
    text = re.sub(r"\[[^\]]+\]", " ", text or "")
    text = re.sub(r"^(映像|字幕|Grock|GPT|GMN|YT|話者|ナレーション)\s*[：:]", "", text.strip())
    text = re.sub(r"\s+", " ", text).strip(" 　-—:：。、「」[]")
    if not text:
        return fallback
    if len(text) > 32:
        text = text[:31].rstrip() + "..."
    return text


def _chapter_title_from_scene(scene: dict, index: int) -> str:
    fallback = "導入" if index == 0 else f"論点{index}"
    candidates = [
        scene.get("subtitle"),
        scene.get("overlay_text"),
        scene.get("visual_prompt"),
        scene.get("narration"),
    ]
    for turn in scene.get("dialogue") or []:
        candidates.append(turn.get("text"))
    for candidate in candidates:
        title = _clean_chapter_title(str(candidate or ""), fallback)
        if title != fallback:
            return title
    return fallback


def _build_chapters(project: dict, scenes: list[dict], final_duration: float, intro_offset: float = 0.0) -> list[dict]:
    if project.get("format") != "standard_landscape" or final_duration < LONG_FORM_CHAPTER_MIN_DURATION:
        return []
    usable = [s for s in scenes if float(s.get("actual_end") or s.get("duration") or 0) > 0]
    if not usable:
        return []

    first_title = _chapter_title_from_scene(usable[0], 0)
    chapters = [{"time": 0.0, "title": "オープニング" if intro_offset >= 1.0 else first_title}]
    last_time = 0.0
    if intro_offset >= 10.0:
        chapters.append({"time": intro_offset, "title": first_title})
        last_time = intro_offset

    next_target = max(last_time + CHAPTER_TARGET_GAP_SECONDS, CHAPTER_TARGET_GAP_SECONDS)
    for idx, scene in enumerate(usable[1:], start=1):
        if len(chapters) >= CHAPTER_MAX_COUNT:
            break
        start = intro_offset + float(scene.get("actual_start") or 0.0)
        if start < 5.0 or start >= max(0.0, final_duration - 10.0):
            continue
        title = _chapter_title_from_scene(scene, idx)
        strong_break = bool(re.search(r"(第[一二三四五六七八九十0-9]+|章|Part|SECTION|セクション|まとめ|結論|警告|号外)", title, re.I))
        if (start >= next_target and start - last_time >= CHAPTER_MIN_GAP_SECONDS) or (strong_break and start - last_time >= CHAPTER_MIN_GAP_SECONDS):
            chapters.append({"time": start, "title": title})
            last_time = start
            next_target = start + CHAPTER_TARGET_GAP_SECONDS

    if len(chapters) < 3:
        desired = min(CHAPTER_MAX_COUNT, max(3, int(final_duration // CHAPTER_TARGET_GAP_SECONDS)))
        for slot in range(1, desired):
            target = final_duration * slot / desired
            best = min(
                usable,
                key=lambda s: abs((intro_offset + float(s.get("actual_start") or 0.0)) - target),
            )
            start = intro_offset + float(best.get("actual_start") or 0.0)
            if start >= 5.0 and all(abs(start - c["time"]) >= CHAPTER_MIN_GAP_SECONDS for c in chapters):
                chapters.append({"time": start, "title": _chapter_title_from_scene(best, slot)})

    chapters = sorted(chapters, key=lambda c: c["time"])[:CHAPTER_MAX_COUNT]
    deduped = []
    for chapter in chapters:
        if deduped and chapter["time"] - deduped[-1]["time"] < 10.0:
            continue
        deduped.append(chapter)
    if len(deduped) < 2:
        return []
    return deduped


def _write_long_form_chapters(project: dict, scenes: list[dict], final_dir: Path, final_video: Path, intro_offset: float = 0.0) -> dict:
    final_duration = probe_duration(final_video)
    chapters = _build_chapters(project, scenes, final_duration, intro_offset)
    if not chapters:
        return {}

    txt_path = final_dir / "chapters.txt"
    json_path = final_dir / "chapters.json"
    metadata_path = final_dir / "chapters.ffmetadata"
    embedded_path = final_dir / "final_with_chapters.mp4"

    txt_path.write_text(
        "\n".join(f"{_format_chapter_time(c['time'])} {c['title']}" for c in chapters) + "\n",
        encoding="utf-8",
    )
    write_json(json_path, {"chapters": chapters, "duration": final_duration})

    metadata = [";FFMETADATA1"]
    for idx, chapter in enumerate(chapters):
        start_ms = int(chapter["time"] * 1000)
        end_seconds = chapters[idx + 1]["time"] if idx + 1 < len(chapters) else final_duration
        end_ms = max(start_ms + 1000, int(end_seconds * 1000))
        title = str(chapter["title"]).replace("\\", "\\\\").replace("=", "\\=")
        metadata.extend([
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={title}",
        ])
    metadata_path.write_text("\n".join(metadata) + "\n", encoding="utf-8")

    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(final_video),
            "-i", str(metadata_path),
            "-map_metadata", "1",
            "-map_chapters", "1",
            "-codec", "copy",
            str(embedded_path),
        ], check=True)
        embedded_path.replace(final_video)
    except Exception as e:
        print(f"[tasks] chapter metadata embed skipped: {e}")

    return {
        "chapters_path": str(txt_path),
        "chapters_json_path": str(json_path),
        "chapters_url": f"/api/projects/{project.get('project_id')}/chapters",
        "chapters_json_url": f"/api/projects/{project.get('project_id')}/chapters.json",
    }


def _scene_voice_kwargs(project: dict, scene: dict, turn: dict | None = None) -> dict:
    profile = get_voice_profile((turn or {}).get("speaker") or scene.get("speaker")) or {}
    project_speaker = project.get("voice_speaker_id")
    is_short = project.get("format") == "short_vertical"
    qwen3_tts_instruct = profile.get("qwen3_tts_instruct", scene.get("qwen3_tts_instruct", project.get("qwen3_tts_instruct")))
    speed_scale = profile.get("speed_scale", scene.get("tts_speed_scale", project.get("tts_speed_scale", 1.0)))
    if is_short:
        qwen3_tts_instruct = profile.get("qwen3_tts_short_instruct", qwen3_tts_instruct)
        speed_scale = profile.get("short_speed_scale", speed_scale)
    return {
        "tts_engine": profile.get("tts_engine", scene.get("tts_engine", project.get("tts_engine", TTS_ENGINE))),
        "speaker_id": profile.get("speaker_id", project_speaker if project_speaker is not None else DEFAULT_TTS_SPEAKER_ID),
        "model_id": profile.get("model_id", scene.get("tts_model_id", project.get("tts_model_id"))),
        "style": profile.get("style", scene.get("tts_style", project.get("tts_style"))),
        "style_weight": profile.get("style_weight", scene.get("tts_style_weight", project.get("tts_style_weight"))),
        "sdp_ratio": profile.get("sdp_ratio", scene.get("tts_sdp_ratio", project.get("tts_sdp_ratio"))),
        "noise": profile.get("noise", scene.get("tts_noise", project.get("tts_noise"))),
        "noisew": profile.get("noisew", scene.get("tts_noisew", project.get("tts_noisew"))),
        "language": profile.get("language", scene.get("tts_language", project.get("tts_language"))),
        "qwen3_tts_model": profile.get("qwen3_tts_model", scene.get("qwen3_tts_model", project.get("qwen3_tts_model"))),
        "qwen3_tts_mode": profile.get("qwen3_tts_mode", scene.get("qwen3_tts_mode", project.get("qwen3_tts_mode"))),
        "qwen3_tts_speaker": profile.get("qwen3_tts_speaker", scene.get("qwen3_tts_speaker", project.get("qwen3_tts_speaker"))),
        "qwen3_tts_instruct": qwen3_tts_instruct,
        "speed_scale": speed_scale,
    }


_TTS_CLIENT_CACHE = {}


def _tts_for_voice(default_tts, voice: dict):
    engine = (voice.get("tts_engine") or TTS_ENGINE).lower().replace("-fallback", "")
    if engine == TTS_ENGINE and default_tts is not None:
        return default_tts
    if engine not in _TTS_CLIENT_CACHE:
        _TTS_CLIENT_CACHE[engine] = get_tts_client(engine)
    return _TTS_CLIENT_CACHE[engine]


def _synthesize_with_voice(default_tts, voice: dict, text: str, out_path: Path, speed: float, volume: float):
    tts = _tts_for_voice(default_tts, voice)
    effective_speed = float(speed) * float(voice.get("speed_scale") or 1.0)
    return tts.synthesize(
        text, out_path,
        speaker_id=voice["speaker_id"], speed_scale=effective_speed, volume_scale=volume,
        model_id=voice["model_id"],
        style=voice["style"],
        style_weight=voice["style_weight"],
        sdp_ratio=voice["sdp_ratio"],
        noise=voice["noise"],
        noisew=voice["noisew"],
        language=voice.get("language", "Japanese"),
        qwen3_tts_model=voice.get("qwen3_tts_model"),
        qwen3_tts_mode=voice.get("qwen3_tts_mode"),
        qwen3_tts_speaker=voice.get("qwen3_tts_speaker"),
        qwen3_tts_instruct=voice.get("qwen3_tts_instruct"),
    )


def _make_silence(path: Path, duration: float):
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(duration), str(path)
    ], check=True)


def _concat_audio_files(paths: list[Path], list_path: Path, out_path: Path):
    lines = [f"file '{p.as_posix()}'" for p in paths]
    list_path.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-ar", "44100", "-ac", "2", str(out_path)
    ], check=True)


def _mix_audio_files(paths: list[Path], out_path: Path):
    if not paths:
        raise ValueError("No audio files to mix")
    if len(paths) == 1:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(paths[0]),
            "-ar", "44100", "-ac", "2", str(out_path)
        ], check=True)
        return
    inputs = []
    for path in paths:
        inputs.extend(["-i", str(path)])
    streams = "".join(f"[{i}:a]" for i in range(len(paths)))
    gain = round(1 / (len(paths) ** 0.5), 3)
    filter_complex = f"{streams}amix=inputs={len(paths)}:duration=longest:dropout_transition=0,volume={gain}[a]"
    subprocess.run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[a]", "-ar", "44100", "-ac", "2", str(out_path)
    ], check=True)


def _synthesize_scene_audio(tts, project: dict, scene: dict, wav_raw: Path, speed: float, volume: float) -> tuple[list[float], list[dict]]:
    if scene.get("is_flash"):
        text = (scene.get("narration") or "").strip()
        if not text:
            create_flash_sound(wav_raw, float(scene.get("duration") or 1.0))
            return [], [{
                "speaker": "PHF",
                "text": scene.get("flash_word", ""),
                "sound_effect": "boom_glitch",
            }]
        se_wav = wav_raw.with_name(f"{wav_raw.stem}_se.wav")
        tts_wav = wav_raw.with_name(f"{wav_raw.stem}_voice.wav")
        create_flash_sound(se_wav, float(scene.get("duration") or 1.0))
        try:
            voice = _scene_voice_kwargs(project, scene)
            _, mora_fracs = _synthesize_with_voice(tts, voice, text, tts_wav, speed, volume)
            _mix_audio_files([se_wav, tts_wav], wav_raw)
        except Exception:
            traceback.print_exc()
            create_flash_sound(wav_raw, float(scene.get("duration") or 1.0))
            mora_fracs = []
        return mora_fracs, [{
            "speaker": "PHF",
            "text": text,
            "sound_effect": "boom_glitch",
        }]

    dialogue = [d for d in scene.get("dialogue", []) if d.get("text")]
    if not dialogue:
        text = (scene.get("narration") or "").strip()
        if not text:
            _make_silence(wav_raw, float(scene.get("duration") or 0.1))
            return [], [{
                "speaker": scene.get("speaker"),
                "text": "",
                "silent": True,
            }]
        voice = _scene_voice_kwargs(project, scene)
        _, mora_fracs = _synthesize_with_voice(tts, voice, text, wav_raw, speed, volume)
        return mora_fracs, [{
            "speaker": scene.get("speaker"),
            "tts_engine": voice["tts_engine"],
            "model_id": voice["model_id"],
            "speaker_id": voice["speaker_id"],
            "style": voice["style"],
            "style_weight": voice["style_weight"],
            "text": text,
        }]

    turn_dir = wav_raw.parent / f"{wav_raw.stem}_turns"
    turn_dir.mkdir(parents=True, exist_ok=True)

    def synth_turn(index_turn):
        index, turn = index_turn
        voice = _scene_voice_kwargs(project, scene, turn)
        out = turn_dir / f"turn_{index:02d}.wav"
        _synthesize_with_voice(tts, voice, turn["text"], out, speed, volume)
        return index, out, {
            "speaker": turn.get("speaker"),
            "tts_engine": voice["tts_engine"],
            "model_id": voice["model_id"],
            "speaker_id": voice["speaker_id"],
            "style": voice["style"],
            "style_weight": voice["style_weight"],
            "text": turn["text"],
        }

    voices = [_scene_voice_kwargs(project, scene, turn) for turn in dialogue]
    has_qwen3_tts = any((voice.get("tts_engine") or "").lower().replace("-fallback", "") in ("qwen3tts", "qwen3-tts", "qwen") for voice in voices)
    workers = 1 if has_qwen3_tts else max(1, min(TTS_PARALLEL_WORKERS, len(dialogue)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(synth_turn, enumerate(dialogue, start=1)))
    results.sort(key=lambda item: item[0])

    if scene.get("simultaneous_dialogue"):
        turns_debug = [debug for _, _, debug in results]
        _mix_audio_files([audio_path for _, audio_path, _ in results], wav_raw)
        return [], turns_debug

    concat_parts = []
    turns_debug = []
    for pos, (index, audio_path, debug) in enumerate(results):
        concat_parts.append(audio_path)
        turns_debug.append(debug)
        if pos < len(results) - 1 and DIALOGUE_PAUSE_SECONDS > 0:
            pause = turn_dir / f"pause_{index:02d}.wav"
            _make_silence(pause, DIALOGUE_PAUSE_SECONDS)
            concat_parts.append(pause)

    _concat_audio_files(concat_parts, turn_dir / "concat_turns.txt", wav_raw)
    return [], turns_debug


def _get_video_client(model: str = None):
    engine = (model or VIDEO_ENGINE).lower()
    if engine == "runway":
        from services.runway_client import RunwayClient
        return RunwayClient()
    elif engine == "luma":
        from services.luma_client import LumaClient
        return LumaClient()
    elif engine in {"veo_lite", "veo-lite", "google_veo_lite"}:
        from services.veo_client import VeoLiteClient
        return VeoLiteClient()
    elif engine in {"minimax", "hailuo", "minimax_hailuo"}:
        from services.minimax_client import MiniMaxClient
        return MiniMaxClient()
    return None


def _final_call_cache_key(text: str, speech: str, width: int, height: int, fps: int) -> str:
    payload = {
        "text": text.strip(),
        "speech": speech.strip(),
        "width": width,
        "height": height,
        "fps": fps,
        "speaker": "GMN",
        "version": 1,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _ensure_final_call_clip(
    tts,
    project: dict,
    text: str,
    speech: str,
    width: int,
    height: int,
    fps: int,
    speed: float,
    volume: float,
) -> Path:
    FINAL_CALL_DIR.mkdir(parents=True, exist_ok=True)
    key = _final_call_cache_key(text, speech, width, height, fps)
    clip = FINAL_CALL_DIR / f"{key}.mp4"
    manifest = FINAL_CALL_DIR / f"{key}.json"
    if clip.exists():
        print(f"[final-call] cache hit: {clip.name}")
        return clip

    work_dir = FINAL_CALL_DIR / f"{key}_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_wav = work_dir / "speech_raw.wav"
    scene = {"speaker": "GMN", "narration": speech}
    voice = _scene_voice_kwargs(project, scene)
    _synthesize_with_voice(tts, voice, speech, raw_wav, speed, volume)
    duration = max(2.4, probe_duration(raw_wav) + 0.65)
    create_final_call_clip(text, raw_wav, clip, width, height, fps, duration)
    write_json(manifest, {
        "key": key,
        "text": text,
        "speech": speech,
        "width": width,
        "height": height,
        "fps": fps,
        "duration": round(duration, 3),
        "path": str(clip),
        "voice": voice,
    })
    return clip


def generate_video(project_id: str):
    pdir = project_dir(project_id)
    try:
        project = read_json(pdir / "project.json")
        output_width, output_height, output_fps, runway_ratio = _output_settings(project)
        selected_model = (project.get("model") or VIDEO_ENGINE).lower()
        set_status(project_id, "planning", 5, "シーン構成を作成中")

        scenes = build_scenes(project)
        write_json(pdir / "scenes.json", {"scenes": scenes})

        clip_dir = pdir / "clips"
        audio_dir = pdir / "audio"
        subtitle_dir = pdir / "subtitles"
        final_dir = pdir / "final"
        for d in [clip_dir, audio_dir, subtitle_dir, final_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 1. 映像生成
        check_cancel(project_id)
        raw_clips = []
        bumper_dir = STORAGE_DIR / "assets" / "bumpers"
        background_filename = project.get("background_video_filename", "")
        background_video_path = bumper_dir / background_filename if background_filename else None
        if background_video_path and not background_video_path.exists():
            print(f"[tasks] background video not found: {background_video_path}")
            background_video_path = None
        try:
            video_client = _get_video_client(selected_model)
        except Exception as e:
            if selected_model in REMOTE_VIDEO_MODELS:
                set_status(project_id, "failed", 5, f"{selected_model.upper()}初期化失敗: {e}")
                raise
            video_client = None
            print(f"[tasks] 映像クライアント初期化失敗: {e}")

        for i, scene in enumerate(scenes, start=1):
            check_cancel(project_id)
            base_progress = 5 + int(35 * (i - 1) / max(1, len(scenes)))
            scene_range = 35 // max(1, len(scenes))
            set_status(project_id, "generating_video", base_progress, f"シーン{i}/{len(scenes)}の映像を生成中")
            raw = clip_dir / f"scene_{i:02d}_raw.mp4"
            scene_cache_payload = _scene_clip_cache_payload(
                project,
                scene,
                selected_model,
                output_width,
                output_height,
                output_fps,
                background_video_path,
            )
            restored_from_cache = (
                _load_scene_clip_cache(scene_cache_payload, raw)
                or _load_prior_project_scene_clip(project_id, scene_cache_payload, raw)
            )

            if restored_from_cache:
                set_status(project_id, "generating_video", base_progress, f"シーン{i}: 既存素材をコピーして使用")

            elif scene.get("is_flash"):
                def progress_callback(pct, message, _base=base_progress, _range=scene_range, _i=i, _total=len(scenes)):
                    mapped = _base + int(_range * pct / 100)
                    set_status(project_id, "generating_video", mapped, f"PHF {_i}/{_total}: {message}")

                set_status(project_id, "generating_video", base_progress, f"シーン{i}: PHFフラッシュ生成中")
                ensure_flash_visual_clip(
                    raw,
                    scene.get("flash_word") or "PHF",
                    scene.get("flash_prompt") or scene.get("visual_prompt") or "cinematic glitch flash",
                    output_width,
                    output_height,
                    output_fps,
                    video_client=video_client,
                    use_runway=selected_model in REMOTE_VIDEO_MODELS,
                    negative_prompt=scene.get("negative_prompt", ""),
                    ratio=runway_ratio,
                    progress_callback=progress_callback,
                )

            elif is_graphic_mode(scene.get("visual_prompt", "")):
                set_status(project_id, "generating_video", base_progress, f"シーン{i}: グラフィック生成中（Runway対象外）")
                try:
                    create_graphic_clip(raw, scene, output_width, output_height, output_fps, background_video_path)
                except Exception as e:
                    set_status(project_id, "generating_video", base_progress, f"グラフィック失敗: {e}")
                    create_mock_clip(raw, scene, output_width, output_height, output_fps)

            elif video_client:
                def progress_callback(pct, message, _base=base_progress, _range=scene_range, _i=i, _total=len(scenes)):
                    mapped = _base + int(_range * pct / 100)
                    set_status(project_id, "generating_video", mapped, f"シーン{_i}/{_total}: {message}")
                try:
                    try:
                        video_client.generate_clip(
                            scene["visual_prompt"],
                            scene.get("negative_prompt", ""),
                            raw,
                            progress_callback=progress_callback,
                            ratio=runway_ratio,
                            width=output_width,
                            height=output_height,
                        )
                    except TypeError:
                        video_client.generate_clip(
                            scene["visual_prompt"],
                            scene.get("negative_prompt", ""),
                            raw,
                            progress_callback=progress_callback,
                        )
                except Exception as e:
                    if selected_model in REMOTE_VIDEO_MODELS:
                        set_status(project_id, "failed", base_progress, f"{selected_model.upper()}生成失敗: {e}")
                        raise
                    set_status(project_id, "generating_video", base_progress, f"映像生成失敗、モック切替: {e}")
                    create_mock_clip(raw, scene, output_width, output_height, output_fps)
            else:
                if background_video_path:
                    normalize_clip(background_video_path, raw, output_width, output_height, output_fps, scene["duration"])
                else:
                    create_mock_clip(raw, scene, output_width, output_height, output_fps)

            if not restored_from_cache:
                _save_scene_clip_cache(scene_cache_payload, raw)

            normalized = clip_dir / f"scene_{i:02d}.mp4"
            normalize_clip(raw, normalized, output_width, output_height, output_fps, scene["duration"])
            scene_final_hold_seconds = _scene_final_hold_seconds(project, scene, i == len(scenes))
            if scene_final_hold_seconds > 0:
                held_clip = clip_dir / f"scene_{i:02d}_held.mp4"
                normalized = hold_last_frame(normalized, held_clip, scene_final_hold_seconds)

            if scene.get("insert_video_id"):
                insert_clip = clip_dir / f"scene_{i:02d}_insert.mp4"
                normalized = apply_insert_overlay(normalized, scene, insert_clip, output_width, output_height, output_fps)

            overlay_text = scene.get("overlay_text", "").strip()
            if overlay_text:
                overlay_clip = clip_dir / f"scene_{i:02d}_overlay.mp4"
                overlay_placement = "corner_note" if is_graphic_mode(scene.get("visual_prompt", "")) else "center"
                normalized = burn_text_overlay(
                    normalized,
                    overlay_text,
                    overlay_clip,
                    output_width,
                    output_height,
                    placement=overlay_placement,
                )

            raw_clips.append(normalized)

        # 2. ナレーション生成
        check_cancel(project_id)
        set_status(project_id, "generating_audio", 45, "日本語ナレーションを生成中")
        tts = get_tts_client()
        scene_wavs = []
        project_speaker = project.get("voice_speaker_id")
        speaker = project_speaker if project_speaker is not None else DEFAULT_TTS_SPEAKER_ID
        speed = float(project.get("voice_speed_scale") or DEFAULT_VOICE_SPEED)
        if project.get("format") == "short_vertical" and not _is_qwen3_engine(project.get("tts_engine", TTS_ENGINE)):
            speed = min(1.40, max(speed, SHORT_VERTICAL_MIN_VOICE_SPEED))
        volume = float(project.get("narration_volume") or 1.0)
        current_time = 0.0
        audio_debug = []
        dynamic_duration_extended = False

        for i, scene in enumerate(scenes, start=1):
            wav_raw = audio_dir / f"scene_{i:02d}_raw.wav"
            wav_fit = audio_dir / f"scene_{i:02d}.wav"
            mora_fracs = []
            turns_debug = []
            tts_error = ""
            try:
                mora_fracs, turns_debug = _synthesize_scene_audio(tts, project, scene, wav_raw, speed, volume)
            except Exception as e:
                tts_error = f"{type(e).__name__}: {e}"
                traceback.print_exc()
                if TTS_ENGINE in ("stylebertvits2", "style-bert-vits2", "sbv2", "qwen3tts", "qwen3-tts", "qwen"):
                    audio_debug.append({
                        "scene_id": scene.get("scene_id"),
                        "target_sec": scene["duration"],
                        "tts_engine": TTS_ENGINE,
                        "tts_error": tts_error,
                        "dialogue_turns": turns_debug,
                    })
                    write_json(pdir / "scenes.json", {"scenes": scenes, "audio_debug": audio_debug})
                    raise RuntimeError(f"TTS synthesis failed for scene {i}: {tts_error}") from e
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", str(scene["duration"]), str(wav_raw)
                ], check=True)

            target_duration = float(scene["duration"])
            scene_final_hold_seconds = _scene_final_hold_seconds(project, scene, i == len(scenes))
            target_duration += scene_final_hold_seconds

            raw_duration = probe_duration(wav_raw)
            original_audio_target_duration = target_duration
            audio_target_adjustment = ""
            reinforcement_count = 0
            if _should_reinforce_fixed_short_scene(project, scene, raw_duration, target_duration):
                phrase = _compact_emphasis_phrase(scene)
                if phrase:
                    reinforce_dir = audio_dir / f"scene_{i:02d}_reinforce"
                    reinforce_dir.mkdir(parents=True, exist_ok=True)
                    concat_parts = [wav_raw]
                    voice = _scene_voice_kwargs(project, scene)
                    reinforce_speed = min(float(speed), FIXED_SHORT_REINFORCE_SPEED_SCALE)
                    max_repeats = max(0, FIXED_SHORT_REINFORCE_MAX_REPEATS)
                    for repeat_index in range(max_repeats):
                        if target_duration - raw_duration < FIXED_SHORT_REINFORCE_GAP_SECONDS:
                            break
                        pause = reinforce_dir / f"pause_{repeat_index + 1:02d}.wav"
                        emphasis = reinforce_dir / f"emphasis_{repeat_index + 1:02d}.wav"
                        _make_silence(pause, 0.55)
                        emphasis_text = f"{phrase}。"
                        _synthesize_with_voice(tts, voice, emphasis_text, emphasis, reinforce_speed, volume)
                        concat_parts.extend([pause, emphasis])
                        raw_duration += probe_duration(pause) + probe_duration(emphasis)
                        reinforcement_count += 1
                    if reinforcement_count:
                        reinforced_wav = audio_dir / f"scene_{i:02d}_reinforced.wav"
                        _concat_audio_files(concat_parts, reinforce_dir / "concat_reinforce.txt", reinforced_wav)
                        wav_raw = reinforced_wav
                        raw_duration = probe_duration(wav_raw)
                        audio_target_adjustment = f"reinforce_key_phrase_x{reinforcement_count}"
                        if scene.get("subtitle"):
                            scene["subtitle"] = f"{scene['subtitle']}\n再確認：{phrase}"
                        elif scene.get("narration"):
                            scene["subtitle"] = f"再確認：{phrase}"
            max_compression = max(1.0, AUDIO_MAX_TEMPO_COMPRESSION)
            if raw_duration > target_duration * max_compression:
                original_target_duration = target_duration
                target_duration = round(raw_duration / max_compression, 3)
                audio_target_adjustment = "extend_for_long_tts"
                scene_hold = scene_final_hold_seconds
                scene["duration"] = round(max(0.1, target_duration - scene_hold), 3)
                scene["end"] = round(float(scene.get("start") or 0.0) + float(scene["duration"]), 3)
                adjusted_clip = clip_dir / f"scene_{i:02d}_duration_adjusted.mp4"
                force_media_duration(raw_clips[i - 1], adjusted_clip, target_duration)
                raw_clips[i - 1] = adjusted_clip
                dynamic_duration_extended = True
                print(
                    f"[audio] scene {i} target extended "
                    f"{original_target_duration:.3f}s -> {target_duration:.3f}s "
                    f"to avoid tempo>{max_compression:.2f}"
                )
            else:
                max_tail_pad = max(0.0, AUDIO_MAX_TAIL_PAD_SECONDS)
                preserve_fixed_short_timing = (
                    project.get("format") == "short_vertical"
                    and project.get("short_timing_mode", "fixed_57") in FIXED_SHORT_TARGET_DURATIONS
                )
                if not preserve_fixed_short_timing and raw_duration + max_tail_pad < target_duration:
                    original_target_duration = target_duration
                    subtitle_read_duration = _readable_text_duration(scene.get("subtitle"))
                    narration_read_duration = _readable_text_duration(scene.get("narration"))
                    target_duration = round(
                        max(
                            AUDIO_MIN_SCENE_DURATION,
                            raw_duration + max_tail_pad,
                            min(original_target_duration, subtitle_read_duration),
                            min(original_target_duration, narration_read_duration),
                        ),
                        3,
                    )
                    if target_duration + 0.05 < original_target_duration:
                        audio_target_adjustment = "shorten_tail_silence"
                        scene_hold = scene_final_hold_seconds
                        scene["duration"] = round(max(0.1, target_duration - scene_hold), 3)
                        scene["end"] = round(float(scene.get("start") or 0.0) + float(scene["duration"]), 3)
                        adjusted_clip = clip_dir / f"scene_{i:02d}_duration_adjusted.mp4"
                        force_media_duration(raw_clips[i - 1], adjusted_clip, target_duration)
                        raw_clips[i - 1] = adjusted_clip
                        print(
                            f"[audio] scene {i} target shortened "
                            f"{original_target_duration:.3f}s -> {target_duration:.3f}s "
                            f"to avoid tail silence>{max_tail_pad:.2f}s"
                        )
            fit_audio_to_duration(wav_raw, wav_fit, target_duration)
            wav_scene_norm = audio_dir / f"scene_{i:02d}_norm.wav"
            normalize_scene_audio(wav_fit, wav_scene_norm)
            if _is_analystk_scene(scene):
                wav_scene_clean = audio_dir / f"scene_{i:02d}_clean.wav"
                clean_analystk_audio(wav_scene_norm, wav_scene_clean)
                wav_scene_norm = wav_scene_clean
            wav_fit = wav_scene_norm
            fit_duration = probe_duration(wav_fit)

            scene["actual_start"] = round(current_time, 3)
            scene["actual_end"] = round(current_time + target_duration, 3)
            scene["_mora_fracs"] = mora_fracs
            current_time += target_duration

            audio_debug.append({
                "scene_id": scene.get("scene_id"),
                "raw_audio_sec": round(raw_duration, 3),
                "target_sec": target_duration,
                "original_target_sec": round(original_audio_target_duration, 3),
                "audio_target_adjustment": audio_target_adjustment,
                "reinforcement_count": reinforcement_count,
                "fitted_audio_sec": round(fit_duration, 3),
                "tempo_compression": round(raw_duration / max(0.01, target_duration), 3),
                "tts_engine": TTS_ENGINE,
                "tts_error": tts_error,
                "dialogue_turns": turns_debug,
            })
            scene_wavs.append(wav_fit)

        narration = audio_dir / "narration.wav"
        concat_audios(scene_wavs, narration)
        narration_stable = audio_dir / "narration_stable.wav"
        stabilize_narration_audio(narration, narration_stable)
        narration = narration_stable

        _apply_analystk_lipsync(
            project_id=project_id,
            project=project,
            scenes=scenes,
            raw_clips=raw_clips,
            scene_wavs=scene_wavs,
            clip_dir=clip_dir,
            output_width=output_width,
            output_height=output_height,
            output_fps=output_fps,
        )

        write_json(pdir / "scenes.json", {"scenes": scenes, "audio_debug": audio_debug})

        # 3. 字幕作成（タイプライター・グラフィック位置対応）
        check_cancel(project_id)
        set_status(project_id, "subtitles", 60, "日本語字幕を作成中")
        ass_path = subtitle_dir / "subtitles.ass"
        srt_path = subtitle_dir / "subtitles.srt"
        subtitle_font_size = int(project.get("subtitle_font_size") or DEFAULT_SUBTITLE_FONT_SIZE)
        write_ass_subtitles(
            scenes, ass_path, output_width, output_height,
            font_size=subtitle_font_size,
            wrap_chars=project.get("subtitle_wrap_chars"),
            max_lines=project.get("subtitle_max_lines"),
            position_from_bottom_pct=project.get("subtitle_position_from_bottom_pct"),
            typewriter=project.get("typewriter_subtitle", True),
            layout=(
                "explain_left"
                if project.get("format") == "standard_landscape"
                and project.get("analystk_lipsync_display_mode") == "explain_right"
                else "default"
            ),
        )
        write_srt_subtitles(
            scenes, srt_path,
            wrap_chars=project.get("subtitle_wrap_chars"),
            max_lines=project.get("subtitle_max_lines"),
        )

        # 4. 動画結合
        check_cancel(project_id)
        set_status(project_id, "combining", 70, "映像カットを結合中")
        if project.get("format") == "standard_landscape" and project.get("standard_timing_mode") == "script_unbounded":
            rendered_duration = max(0.1, round(current_time, 3))
        else:
            rendered_duration = max(float(project["duration"]), round(current_time, 3))
        base_video = final_dir / "video_base.mp4"
        concat_videos(raw_clips, base_video, output_width, output_height, output_fps, rendered_duration)

        # 5. 音声合成
        set_status(project_id, "muxing", 80, "音声を合成中")
        with_audio = final_dir / "video_with_audio.mp4"
        mux_audio(base_video, narration, with_audio, rendered_duration)

        audio_source = with_audio

        # 6. BGM追加
        scene_bgm_enabled = any(scene.get("bgm_filename") or scene.get("bgm") for scene in scenes)
        bgm_enabled = project.get("bgm", False)
        bgm_auto = project.get("bgm_auto", True)
        if scene_bgm_enabled:
            set_status(project_id, "bgm", 83, "台本指定BGMをシーンごとに合成中")
            with_bgm = final_dir / "video_with_scene_bgm.mp4"
            result = add_scene_bgms(with_audio, scenes, with_bgm, rendered_duration)
            if result != with_audio:
                audio_source = with_bgm
        elif bgm_enabled:
            set_status(project_id, "bgm", 83, "BGMを合成中")
            bgm_filename = Path(project.get("bgm_filename") or "").name
            bgm_path_selected = (STORAGE_DIR / "assets" / "bgm" / bgm_filename) if bgm_filename else None
            bgm_path_manual = bgm_path_selected if bgm_path_selected and bgm_path_selected.exists() else STORAGE_DIR / "assets" / "bgm.mp3"
            if bgm_path_manual.exists() and (bgm_filename or not bgm_auto):
                # 選択BGMがある場合は最優先。未選択で自動選択OFFなら従来の bgm.mp3 を使う。
                with_bgm = final_dir / "video_with_bgm.mp4"
                add_bgm(with_audio, bgm_path_manual, with_bgm, rendered_duration)
                audio_source = with_bgm
            else:
                # 自動選択（手動BGMがあればディレクトリ選択より優先）
                with_bgm = final_dir / "video_with_bgm.mp4"
                result = add_bgm_auto(with_audio, scenes, with_bgm, rendered_duration)
                if result != with_audio:
                    audio_source = with_bgm

        # 7. 字幕焼き込み
        if project.get("subtitle", True):
            set_status(project_id, "rendering", 87, "字幕を焼き込み中")
            with_subtitle = final_dir / "video_with_subtitle.mp4"
            burn_ass_subtitles(audio_source, ass_path, with_subtitle)
            audio_source = with_subtitle

        # 8. ロゴ合成
        logo_filename = project.get("logo_filename", "")
        if logo_filename:
            logo_path = STORAGE_DIR / "assets" / "logos" / logo_filename
            if logo_path.exists():
                set_status(project_id, "logo", 93, "ロゴを合成中")
                with_logo = final_dir / "video_with_logo.mp4"
                result = overlay_logo(audio_source, logo_path, with_logo, output_width, output_height)
                if result == with_logo:
                    audio_source = with_logo

        # 9. 前後の既成動画を連結
        intro_filename = project.get("intro_video_filename", "")
        outro_filename = project.get("outro_video_filename", "")
        concat_parts = []
        intro_offset_seconds = 0.0
        if intro_filename:
            intro_path = bumper_dir / intro_filename
            if intro_path.exists():
                set_status(project_id, "bumper", 96, "前動画を正規化中")
                intro_norm = final_dir / "intro_normalized.mp4"
                normalize_video_for_concat(intro_path, intro_norm, output_width, output_height, output_fps)
                concat_parts.append(intro_norm)
                intro_offset_seconds = probe_duration(intro_norm)
            else:
                print(f"[tasks] intro bumper not found: {intro_path}")

        main_norm = final_dir / "main_normalized.mp4"
        normalize_video_for_concat(audio_source, main_norm, output_width, output_height, output_fps)
        concat_parts.append(main_norm)

        if outro_filename:
            outro_path = bumper_dir / outro_filename
            if outro_path.exists():
                set_status(project_id, "bumper", 97, "後動画を正規化中")
                outro_norm = final_dir / "outro_normalized.mp4"
                normalize_video_for_concat(outro_path, outro_norm, output_width, output_height, output_fps)
                concat_parts.append(outro_norm)
            else:
                print(f"[tasks] outro bumper not found: {outro_path}")

        # 10. 最終ファイルを作成
        final_video = final_dir / "final.mp4"
        if len(concat_parts) > 1:
            set_status(project_id, "bumper", 98, "前後動画を連結中")
            concat_media_files(concat_parts, final_video)
        elif main_norm != final_video:
            subprocess.run(["cp", str(main_norm), str(final_video)], check=True)

        head_title = (project.get("head_title") or "").strip()
        if project.get("format") == "standard_landscape" and head_title:
            set_status(project_id, "head_title", 99, "ヘッドタイトルを合成中")
            titled_video = final_dir / "final_with_head_title.mp4"
            burn_head_title(final_video, head_title, titled_video, output_width, output_height, 3.0)
            titled_video.replace(final_video)

        final_call_enabled = project.get("format") != "short_vertical"
        final_call_text = (project.get("final_call_text") or "").strip() if final_call_enabled else ""
        final_call_speech = (project.get("final_call_speech") or final_call_text).strip() if final_call_enabled else ""
        if final_call_text and final_call_speech:
            set_status(project_id, "final_call", 99, "最終コールを追加中")
            final_call_clip = _ensure_final_call_clip(
                tts,
                project,
                final_call_text,
                final_call_speech,
                output_width,
                output_height,
                output_fps,
                speed,
                volume,
            )
            final_norm = final_dir / "final_before_call_normalized.mp4"
            call_norm = final_dir / "final_call_normalized.mp4"
            normalize_video_for_concat(final_video, final_norm, output_width, output_height, output_fps)
            normalize_video_for_concat(final_call_clip, call_norm, output_width, output_height, output_fps)
            with_call = final_dir / "final_with_call.mp4"
            concat_media_files([final_norm, call_norm], with_call)
            with_call.replace(final_video)

        if project.get("format") == "short_vertical":
            fixed_target_duration = FIXED_SHORT_TARGET_DURATIONS.get(project.get("short_timing_mode", "fixed_57"))
            target_duration = fixed_target_duration if fixed_target_duration is not None else round(current_time, 3)
            current_duration = probe_duration(final_video)
            if fixed_target_duration is not None and (
                current_duration + 0.05 < target_duration
                or (not dynamic_duration_extended and abs(current_duration - target_duration) > 0.05)
            ):
                exact_final = final_dir / "final_exact_duration.mp4"
                force_media_duration(final_video, exact_final, target_duration)
                exact_final.replace(final_video)
            elif current_duration + 0.05 < target_duration:
                exact_final = final_dir / "final_exact_duration.mp4"
                force_media_duration(final_video, exact_final, target_duration)
                exact_final.replace(final_video)

        set_status(project_id, "chapters", 99, "長尺セクションを設定中")
        chapter_files = _write_long_form_chapters(project, scenes, final_dir, final_video, intro_offset_seconds)

        thumbnail_time = float(project.get("thumbnail_time_seconds") or 0.0)
        thumbnail_path = final_dir / "thumbnail.jpg"
        extract_thumbnail(final_video, thumbnail_path, thumbnail_time)

        set_status(
            project_id,
            "completed",
            100,
            "完成しました",
            final_path=str(final_video),
            thumbnail_path=str(thumbnail_path),
            final_call_asset=str(final_call_clip) if final_call_text and final_call_speech else "",
            **chapter_files,
        )
        return {"project_id": project_id, "final_path": str(final_video)}

    except VideoGenerationCancelled:
        (project_dir(project_id) / "cancel.flag").unlink(missing_ok=True)
        set_status(project_id, "cancelled", 0, "ユーザーにより中断されました")
    except Exception as e:
        error_text = traceback.format_exc()
        set_status(project_id, "failed", 100, f"生成に失敗しました: {e}", error=error_text)
        raise
