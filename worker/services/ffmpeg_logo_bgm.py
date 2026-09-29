"""
ffmpeg_service.pyに追加する関数：
- overlay_logo: ロゴ画像を動画上部に合成
- select_bgm: シーン内容からBGMを自動選択
- add_bgm_auto: 自動BGM追加
"""
import os
import subprocess
from pathlib import Path
from typing import List, Dict

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
BGM_DIR = Path(os.getenv("BGM_DIR") or (STORAGE_DIR / "assets" / "bgm"))
BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.15"))
LOGO_HEIGHT = int(os.getenv("LOGO_HEIGHT", "400"))  # ロゴの高さ(px)
LOGO_MARGIN = int(os.getenv("LOGO_MARGIN", "80"))   # ロゴの余白(px)


def run(cmd: List[str]):
    print("RUN:", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def list_bgm_files() -> List[Path]:
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    bgm_files = []
    for suffix in ("*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg", "*.flac"):
        bgm_files.extend(BGM_DIR.glob(suffix))
    return sorted(bgm_files, key=lambda p: p.name.lower())


def resolve_bgm(name: str | None) -> Path | None:
    """登録済みBGMをファイル名または拡張子なしIDで解決する。"""
    requested = (name or "").strip().strip('"').strip("'")
    if not requested or requested.lower() in {"none", "off", "なし", "無し"}:
        return None
    requested = Path(requested.replace("\\", "/")).name
    requested_lower = requested.lower()
    requested_stem = Path(requested).stem.lower()
    for bgm in list_bgm_files():
        if bgm.name.lower() == requested_lower or bgm.stem.lower() == requested_stem:
            return bgm
    return None


def overlay_logo(
    video: Path,
    logo_path: Path,
    out_path: Path,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """ロゴ画像を合成する。標準画面は右上小さめ、ショートは従来通り上部中央。"""
    if not logo_path.exists():
        print(f"[logo] ロゴファイルが見つかりません: {logo_path}")
        return video

    out_path.parent.mkdir(parents=True, exist_ok=True)

    is_standard = width > height
    if is_standard:
        logo_w = int(width * 0.48)
        logo_h = int(height * 0.36)
        margin_x = int(width * 0.025)
        margin_y = int(height * 0.035)
        x_pos = f"W-overlay_w-{margin_x}"
        y_pos = str(margin_y)
    else:
        logo_w = int(width * 0.85)
        logo_h = LOGO_HEIGHT
        x_pos = f"(W-overlay_w)/2"
        y_pos = str(LOGO_MARGIN)

    if is_standard:
        logo_filter = (
            f"scale={logo_w}:-1,"
            f"scale=-1:{logo_h}:force_original_aspect_ratio=decrease,"
            f"format=rgba"
        )
    else:
        logo_filter = (
            f"scale={logo_w}:{logo_h}:force_original_aspect_ratio=decrease,"
            f"format=rgba"
        )

    vf = (
        f"[1:v]{logo_filter}[logo];"
        f"[0:v][logo]overlay={x_pos}:{y_pos}:format=auto"
    )

    run([
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(logo_path),
        "-filter_complex", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path)
    ])
    print(f"[logo] ロゴ合成完了: {out_path}")
    return out_path


def select_bgm(scenes: List[Dict]) -> Path:
    """シーンの内容からBGMファイルを自動選択する"""
    # BGMディレクトリが存在しない場合はデフォルトを返す
    if not BGM_DIR.exists():
        BGM_DIR.mkdir(parents=True, exist_ok=True)
        return None

    # BGMファイル一覧を取得
    bgm_files = list_bgm_files()
    if not bgm_files:
        return None

    # シーンのナレーション・プロンプトから雰囲気を判定
    all_text = " ".join([
        s.get("narration", "") + " " + s.get("visual_prompt", "")
        for s in scenes
    ]).lower()

    # キーワードベースのBGM選択
    bgm_map = {
        "serious": ["serious", "heavy", "dark", "sumi", "documentary", "重", "暗", "墨"],
        "nostalgic": ["nostalgic", "old", "traditional", "wagashi", "和菓子", "老舗", "郷愁"],
        "tension": ["tension", "urgent", "crisis", "問題", "危機", "滞納", "差し押さえ"],
        "calm": ["calm", "quiet", "peaceful", "静", "穏やか"],
    }

    # マッチするBGMカテゴリを探す
    for category, keywords in bgm_map.items():
        if any(kw in all_text for kw in keywords):
            # カテゴリ名を含むファイルを探す
            for bgm in bgm_files:
                if category in bgm.stem.lower():
                    print(f"[bgm] 自動選択: {bgm.name} (category: {category})")
                    return bgm

    # マッチしない場合は最初のファイルを使用
    print(f"[bgm] デフォルト選択: {bgm_files[0].name}")
    return bgm_files[0]


def add_bgm_auto(
    video: Path,
    scenes: List[Dict],
    out_path: Path,
    duration: int,
    volume: float = BGM_VOLUME,
) -> Path:
    """シーン内容に合ったBGMを自動選択して追加する"""
    bgm_path = select_bgm(scenes)
    if not bgm_path:
        print("[bgm] BGMファイルなし、スキップ")
        return video

    out_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        f"[1:a]volume={volume},"
        f"afade=t=in:st=0:d=0.5,"
        f"afade=t=out:st={max(0, duration-1)}:d=1.0,"
        f"aloop=loop=-1:size=2e+09[a2];"
        f"[0:a][a2]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
    )

    run([
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[a]",
        "-t", str(duration),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path)
    ])
    print(f"[bgm] BGM合成完了: {out_path}")
    return out_path


def add_scene_bgms(
    video: Path,
    scenes: List[Dict],
    out_path: Path,
    duration: int,
    volume: float = BGM_VOLUME,
) -> Path:
    """台本で指定されたBGMをシーン区間ごとに切り替えて合成する。"""
    segments = []
    for scene in scenes:
        bgm_name = scene.get("bgm_filename") or scene.get("bgm")
        if not bgm_name:
            continue
        bgm_path = resolve_bgm(str(bgm_name))
        if not bgm_path:
            print(f"[bgm] scene {scene.get('scene_id')} BGM not found: {bgm_name}")
            continue
        start = float(scene.get("actual_start", scene.get("start", 0)) or 0)
        end = float(scene.get("actual_end", start + float(scene.get("duration", 0) or 0)) or 0)
        seg_duration = max(0.1, end - start)
        segments.append({
            "scene_ids": [scene.get("scene_id")],
            "path": bgm_path,
            "start": max(0.0, start),
            "end": max(0.0, end),
            "duration": seg_duration,
        })

    if not segments:
        print("[bgm] 台本指定BGMなし、スキップ")
        return video

    merged_segments = []
    for segment in segments:
        if merged_segments:
            previous = merged_segments[-1]
            is_same_bgm = previous["path"] == segment["path"]
            is_contiguous = abs(float(previous["end"]) - float(segment["start"])) <= 0.05
            if is_same_bgm and is_contiguous:
                previous["scene_ids"].extend(segment["scene_ids"])
                previous["end"] = segment["end"]
                previous["duration"] = max(0.1, float(previous["end"]) - float(previous["start"]))
                continue
        merged_segments.append(segment)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    inputs = ["ffmpeg", "-y", "-i", str(video)]
    for segment in merged_segments:
        inputs.extend(["-i", str(segment["path"])])

    filter_parts = []
    mix_streams = ["[0:a]"]
    for index, segment in enumerate(merged_segments, start=1):
        label = f"bgm{index}"
        delay_ms = int(round(segment["start"] * 1000))
        seg_duration = float(segment["duration"])
        fade = min(0.5, max(0.05, seg_duration / 3))
        fade_out_start = max(0.0, seg_duration - fade)
        filter_parts.append(
            f"[{index}:a]volume={volume},aloop=loop=-1:size=2e+09,"
            f"atrim=0:{seg_duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d={fade:.3f},"
            f"adelay={delay_ms}:all=1[{label}]"
        )
        mix_streams.append(f"[{label}]")
        print(
            f"[bgm] scenes {segment['scene_ids']}: {segment['path'].name} "
            f"{segment['start']:.3f}s +{seg_duration:.3f}s"
        )

    filter_parts.append(
        f"{''.join(mix_streams)}amix=inputs={len(mix_streams)}:"
        "duration=first:dropout_transition=0:normalize=0[a]"
    )

    run([
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v",
        "-map", "[a]",
        "-t", str(duration),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ])
    print(f"[bgm] 台本指定BGM合成完了: {out_path}")
    return out_path
