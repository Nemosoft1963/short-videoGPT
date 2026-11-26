"""既存のS14完成動画に、台本指定を尊重した全編BGMを付け直す。"""
import argparse
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from services.ffmpeg_logo_bgm import add_scene_bgms, select_bgm
from services.scene_planner import build_scenes


ROOT = Path(os.getenv("STORAGE_DIR", "/storage"))
MANIFEST = ROOT / "batches" / "s14_all_manifest.json"
EXPORT = ROOT / "exports" / "消費税の闇_S14_全20話"


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def repair(episode: dict) -> None:
    number = episode["number"]
    project_dir = ROOT / "projects" / episode["project_id"]
    project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    if project.get("intro_video_filename") or project.get("outro_video_filename"):
        raise ValueError(f"S14-{number}: bumper present; audio timing needs separate handling")
    final_dir = project_dir / "final"
    final = final_dir / "final.mp4"
    narration = final_dir / "video_with_audio.mp4"
    timed_scenes = json.loads((project_dir / "scenes.json").read_text(encoding="utf-8"))["scenes"]
    parsed_scenes = build_scenes(project)
    if len(parsed_scenes) != len(timed_scenes):
        raise ValueError(f"S14-{number}: scene count mismatch")
    for timed, parsed in zip(timed_scenes, parsed_scenes):
        if timed["scene_id"] != parsed["scene_id"]:
            raise ValueError(f"S14-{number}: scene IDs mismatch")
        timed["bgm_filename"] = parsed.get("bgm_filename")
    default_bgm = select_bgm(timed_scenes) if project.get("bgm") else None
    requested = project.get("bgm_filename")
    if requested:
        candidate = ROOT / "assets" / "bgm" / Path(requested).name
        if candidate.exists():
            default_bgm = candidate
    if not default_bgm:
        raise FileNotFoundError(f"S14-{number}: default BGM unavailable")
    final_probe = probe(final)
    narration_probe = probe(narration)
    final_duration = float(final_probe["format"]["duration"])
    narration_duration = float(narration_probe["format"]["duration"])
    if abs(final_duration - narration_duration) > 0.5:
        raise ValueError(f"S14-{number}: duration mismatch {final_duration:.2f}/{narration_duration:.2f}")
    remuxed = final_dir / "bgm_repair_narration.tmp.mp4"
    corrected = final_dir / "bgm_repair_final.tmp.mp4"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(final), "-i", str(narration),
            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", str(remuxed),
        ], check=True)
        add_scene_bgms(remuxed, timed_scenes, corrected, math.ceil(final_duration), default_bgm=default_bgm)
        checked = probe(corrected)
        stream_types = {stream["codec_type"] for stream in checked["streams"]}
        if not {"audio", "video"}.issubset(stream_types):
            raise ValueError(f"S14-{number}: repaired file missing stream")
        if abs(float(checked["format"]["duration"]) - final_duration) > 0.5:
            raise ValueError(f"S14-{number}: repaired duration changed")
        corrected.replace(final)
        export_path = EXPORT / f"S14-{number}_{episode['title']}.mp4"
        shutil.copy2(final, export_path)
        print(f"S14-{number}: repaired {export_path.name} ({default_bgm.name})", flush=True)
    finally:
        remuxed.unlink(missing_ok=True)
        corrected.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--number", help="Only repair one episode, e.g. 01")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for episode in manifest["episodes"]:
        if not args.number or episode["number"] == args.number:
            repair(episode)
