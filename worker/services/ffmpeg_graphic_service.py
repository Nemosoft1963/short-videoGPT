"""
ffmpegグラフィックモード
台本の映像指示に [graphic] タグがある場合、
ffmpegで直接グラフィック映像を生成します。

使い方（台本）:
映像：[graphic:dark_text] 土地2,500万円\nそれでも銀行は貸さない
映像：[graphic:bar_chart] 銀行:1.95% ノンバンク:15%
映像：[graphic:flow] 銀行が貸す→税務署が差し押さえる→銀行が損する
映像：[graphic:sepia] 古い店舗の雰囲気
"""

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

from services.voice_profiles import normalize_speaker

FONT_FILE = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"

# カラーパレット
COLOR_SUMI    = "0x1A1714"   # 墨色（暗い背景）
COLOR_WASHI   = "0xF4EFE6"   # 和紙ベージュ（明るい背景）
COLOR_SHINSHU = "0xB8341C"   # 朱色（強調）
COLOR_WHITE   = "0xFFFFFF"   # 白
COLOR_BLUE    = "0x2A6B9C"
COLOR_GREEN   = "0x4A7C59"
COLOR_GOLD    = "0xD4A017"
COLOR_SEPIA   = "0x8A6A45"

AVATAR_ORDER = ["GMN", "分析官K", "調査員S", "YT", "META", "GPT", "GROCK", "クロード君"]
AVATAR_COLORS = {
    "GMN": COLOR_BLUE,
    "分析官K": "0x2F6F73",
    "調査員S": "0x6E5A8A",
    "YT": "0x4B5D67",
    "META": COLOR_SHINSHU,
    "GPT": COLOR_GOLD,
    "GROCK": "0x8E3B46",
    "CLAUDE": COLOR_SEPIA,
    "クロード君": COLOR_SEPIA,
}
AVATAR_PERSONAS = {
    "GMN": {"face": "G", "role": "HOST"},
    "分析官K": {"face": "K", "role": "LEAD"},
    "調査員S": {"face": "S", "role": "FIELD"},
    "YT": {"face": "Y", "role": "DATA"},
    "META": {"face": "M", "role": "FIELD"},
    "GPT": {"face": "P", "role": "LOGIC"},
    "GROCK": {"face": "X", "role": "ATTACK"},
    "CLAUDE": {"face": "C", "role": "REVIEW"},
    "クロード君": {"face": "C", "role": "REVIEW"},
}

DISPLAY_SPEAKER_NAMES = {
    "AnalystK": "分析官K",
    "Major": "少佐",
    "ANALYST_K": "分析官K",
    "分析官Ｋ": "分析官K",
    "CLAUDE": "クロード君",
    "Claude": "クロード君",
    "クロード": "クロード君",
}


def is_graphic_mode(visual_prompt: str) -> bool:
    return "[graphic" in visual_prompt.lower()


def parse_graphic_tag(visual_prompt: str) -> tuple:
    match = re.search(r'\[graphic(?::([^\]]+))?\]\s*(.*)', visual_prompt, re.DOTALL)
    if match:
        graphic_type = match.group(1) or "dark_text"
        content = match.group(2).strip()
        return graphic_type, content
    return "dark_text", visual_prompt


def run(cmd: List[str]):
    print("GRAPHIC RUN:", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def _escape(text: str) -> str:
    return text.replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")


def _display_units(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1 for ch in text)


def _wrap_visual_line(line: str, max_units: int) -> List[str]:
    wrapped, current, units = [], "", 0
    for ch in (line or "").strip():
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


def _wrap_visual_lines(raw_lines: List[str], max_units: int, max_lines: int) -> List[str]:
    lines: List[str] = []
    for raw in raw_lines:
        lines.extend(_wrap_visual_line(raw, max_units))
    return lines[:max_lines]


def _wrap_visual_lines_with_meta(raw_lines: List[str], max_units: int, max_lines: int) -> List[tuple[str, int, str]]:
    lines: List[tuple[str, int, str]] = []
    for raw_idx, raw in enumerate(raw_lines):
        for wrapped in _wrap_visual_line(raw, max_units):
            lines.append((wrapped, raw_idx, raw))
            if len(lines) >= max_lines:
                return lines
    return lines


def _fit_font_size(
    lines: List[str],
    width: int,
    height: int,
    base_size: int,
    min_size: int,
    max_width_ratio: float = 0.86,
    max_height_ratio: float = 0.36,
) -> int:
    if not lines:
        return base_size
    max_units = max(_display_units(line) for line in lines)
    by_width = int(width * max_width_ratio * 1.72 / max(8, max_units))
    by_height = int(height * max_height_ratio / max(1, len(lines)) * 0.78)
    return max(min_size, min(base_size, by_width, by_height))


def _parse_speaker_list(raw: str) -> List[str]:
    return [_display_speaker_name(speaker.strip()) for speaker in re.split(r"[,+&]", raw or "") if speaker.strip()]


def _display_speaker_name(speaker: str | None) -> str:
    normalized = normalize_speaker((speaker or "").strip())
    return DISPLAY_SPEAKER_NAMES.get(normalized, normalized)


# ──────────────────────────────────────────────
# 背景フィルタ（アニメーション付き）
# ──────────────────────────────────────────────

def _dark_bg_vf(width: int, height: int) -> str:
    """墨色 - 横スクロールする sine 波グラデーション背景（h264 で保存される）"""
    w, h = width, height
    return (
        f"geq="
        f"lum='clip(36+110*sin(2*PI*(X/{w}+T/8))*cos(2*PI*(Y/{h}*0.5+T/14)),4,145)':"
        f"cb='118':cr='130',"
        f"vignette=angle=PI/4"
    )


def _warm_bg_vf(width: int, height: int) -> str:
    """和紙ベージュ - ゆっくりゆらぐ明るい波背景"""
    w, h = width, height
    return (
        f"geq="
        f"lum='clip(218+35*sin(2*PI*(X/{w}*0.8+T/18))*cos(PI*(Y/{h}*0.6+T/22)),165,253)':"
        f"cb='115':cr='132'"
    )


def _sepia_bg_vf(width: int, height: int) -> str:
    """セピア調 - 斜め方向に動く波背景"""
    w, h = width, height
    return (
        f"geq="
        f"lum='clip(113+55*sin(2*PI*(X/{w}*0.7+Y/{h}*0.3+T/14)),55,175)':"
        f"cb='110':cr='145',"
        f"vignette=angle=PI/3"
    )


# ──────────────────────────────────────────────
# 各グラフィッククリップ生成
# ──────────────────────────────────────────────

def create_graphic_clip(
    out_path: Path,
    scene: Dict,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    background_video_path: Optional[Path] = None,
) -> bool:
    visual_prompt = scene.get("visual_prompt", "")
    if not is_graphic_mode(visual_prompt):
        return False

    graphic_type, content = parse_graphic_tag(visual_prompt)
    duration = scene.get("duration", 6)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dispatch = {
        "dark_text":  _create_dark_text_clip,
        "dark_office": _create_dark_text_clip,
        "light_text": _create_light_text_clip,
        "bar_chart":  _create_bar_chart_clip,
        "flow":       _create_flow_clip,
        "title":      _create_title_clip,
        "sepia":      _create_sepia_clip,
    }

    if graphic_type == "meeting_room":
        _create_meeting_room_clip(out_path, content, duration, width, height, fps, background_video_path)
    elif graphic_type.startswith("talkers_"):
        _create_talkers_clip(out_path, content, duration, width, height, fps, _parse_speaker_list(graphic_type.split("_", 1)[1]), background_video_path)
    elif graphic_type.startswith("talker_"):
        _create_talker_clip(out_path, content, duration, width, height, fps, graphic_type.split("_", 1)[1], background_video_path)
    elif graphic_type.startswith("ultra_bold_title"):
        _create_title_clip(out_path, content, duration, width, height, fps, background_video_path)
    else:
        func = dispatch.get(graphic_type, _create_dark_text_clip)
        func(out_path, content, duration, width, height, fps, background_video_path)
    return True


def _run_graphic(out_path, bg_color, vf_filters, duration, width, height, fps, background_video_path: Optional[Path] = None):
    """共通 ffmpeg 実行：アニメ背景 + フィルタチェーン + フェードイン"""
    # リストを破壊しないようコピーして fade を追加
    filters = list(vf_filters)
    if background_video_path:
        # 先頭の自動背景フィルタだけ外し、アップロード動画を下地として使う。
        if filters and filters[0].startswith("geq="):
            filters = filters[1:]
        filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            "setsar=1",
            f"fps={fps}",
            "eq=brightness=-0.08:saturation=0.82",
        ] + filters
    filters = filters + ["fade=t=in:st=0:d=0.4"]
    vf = ",".join(filters)
    if background_video_path:
        run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(background_video_path),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-an", str(out_path)
        ])
    else:
        run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={bg_color}:s={width}x{height}:r={fps}",
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-an", str(out_path)
        ])


def _create_dark_text_clip(out_path, content, duration, width, height, fps, background_video_path: Optional[Path] = None):
    """墨色アニメ背景にテキストを順次フェードイン（重要シーン用）"""
    lines = content.replace("\\n", "\n").split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    wrapped = _wrap_visual_lines_with_meta(lines, max_units=22 if height > width else 34, max_lines=7)
    lines = [line for line, _, _ in wrapped]

    filters = [_dark_bg_vf(width, height)]
    has_strong = any(any(c.isdigit() for c in raw) or any(k in raw for k in ["円", "%", "倍", "万"]) for _, _, raw in wrapped)
    base_size = 82 if has_strong else 64
    size = _fit_font_size(lines, width, height, base_size=base_size, min_size=38)
    line_height = int(size * 1.36)
    y_start = int(height * 0.50 - (len(lines) * line_height) / 2)

    for i, (line, _, raw_line) in enumerate(wrapped):
        delay = round(i * 0.45, 2)
        y = y_start + i * line_height
        if any(c.isdigit() for c in raw_line) or any(k in raw_line for k in ["円", "%", "倍", "万"]):
            color = COLOR_SHINSHU
        else:
            color = COLOR_WHITE
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{_escape(line)}':"
            f"fontsize={size}:fontcolor={color}:"
            f"x=(w-text_w)/2:y={y}:"
            f"box=1:boxcolor={COLOR_SUMI}@0.65:boxborderw=20:"
            f"enable='gte(t,{delay})':alpha='min(1,(t-{delay})/0.35)'"
        )

    _run_graphic(out_path, COLOR_SUMI, filters, duration, width, height, fps, background_video_path)


def _create_light_text_clip(out_path, content, duration, width, height, fps, background_video_path: Optional[Path] = None):
    """和紙ベージュアニメ背景にテキストを順次フェードイン（説明シーン用）"""
    lines = content.replace("\\n", "\n").split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    wrapped = _wrap_visual_lines_with_meta(lines, max_units=24 if height > width else 38, max_lines=7)
    lines = [line for line, _, _ in wrapped]

    filters = [_warm_bg_vf(width, height)]
    has_strong = any(any(k in raw for k in ["→", "＝", "="]) or any(c.isdigit() for c in raw) for _, _, raw in wrapped)
    base_size = 70 if has_strong else 60
    size = _fit_font_size(lines, width, height, base_size=base_size, min_size=34)
    line_height = int(size * 1.36)
    y_start = int(height * 0.50 - (len(lines) * line_height) / 2)

    for i, (line, _, raw_line) in enumerate(wrapped):
        delay = round(i * 0.40, 2)
        y = y_start + i * line_height
        if any(k in raw_line for k in ["→", "＝", "="]) or any(c.isdigit() for c in raw_line):
            color = COLOR_SHINSHU
        else:
            color = COLOR_SUMI
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{_escape(line)}':"
            f"fontsize={size}:fontcolor={color}:"
            f"x=(w-text_w)/2:y={y}:"
            f"enable='gte(t,{delay})':alpha='min(1,(t-{delay})/0.35)'"
        )

    _run_graphic(out_path, COLOR_WASHI, filters, duration, width, height, fps, background_video_path)


def _meeting_room_filters(content, width, height, active_speaker=None):
    if isinstance(active_speaker, (list, tuple, set)):
        active_speakers = {_display_speaker_name(str(s).strip()) for s in active_speaker if str(s).strip()}
    elif active_speaker:
        active_speakers = {_display_speaker_name(str(active_speaker).strip())}
    else:
        active_speakers = set()
    filters = [
        _dark_bg_vf(width, height),
        "drawgrid=width=iw/18:height=ih/12:thickness=1:color=0x2A6B9C@0.10",
    ]
    screen_x = int(width * 0.14)
    screen_y = int(height * 0.10)
    screen_w = int(width * 0.72)
    screen_h = int(height * 0.40)
    filters.extend([
        f"drawbox=x={screen_x-22}:y={screen_y+20}:w={screen_w+44}:h={screen_h+44}:color=0x000000@0.20:t=fill",
        f"drawbox=x={screen_x-10}:y={screen_y-10}:w={screen_w+20}:h={screen_h+20}:color={COLOR_BLUE}@0.07:t=fill",
        f"drawbox=x={screen_x}:y={screen_y}:w={screen_w}:h={screen_h}:color=0x08111B@0.34:t=fill",
        f"drawbox=x={screen_x}:y={screen_y}:w={screen_w}:h={screen_h}:color={COLOR_BLUE}@0.42:t=3",
        f"drawbox=x={screen_x}:y={screen_y}:w={screen_w}:h={int(height*0.095)}:color=0x061018@0.38:t=fill",
        f"drawbox=x={screen_x}:y={screen_y + int(height*0.095)}:w={screen_w}:h=2:color={COLOR_BLUE}@0.36:t=fill",
        f"drawbox=x={int(width*0.08)}:y={int(height*0.62)}:w={int(width*0.84)}:h=2:color={COLOR_BLUE}@0.36:t=fill",
        f"drawbox=x={int(width*0.16)}:y={int(height*0.67)}:w={int(width*0.68)}:h=1:color={COLOR_WHITE}@0.18:t=fill",
    ])

    title = (content or "").replace("\\n", " / ").strip()
    if title:
        title_lines = _wrap_visual_lines([title], max_units=30 if height > width else 48, max_lines=2)
        title_size = _fit_font_size(title_lines, width, height, base_size=max(34, int(height * 0.046)), min_size=24, max_width_ratio=0.62, max_height_ratio=0.11)
        title_line_height = int(title_size * 1.18)
        title_y = screen_y + int(height * 0.022)
        for idx, title_line in enumerate(title_lines):
            filters.append(
                f"drawtext=fontfile='{FONT_BOLD}':text='{_escape(title_line)}':"
                f"fontsize={title_size}:fontcolor={COLOR_WHITE}:"
                f"x=(w-text_w)/2:y={title_y + idx * title_line_height}:"
                f"alpha='min(1,t/0.5)'"
            )

    avatar_w = min(int(width * 0.105), int(width * 0.80 / max(1, len(AVATAR_ORDER))))
    avatar_h = int(height * 0.16)
    gap = min(int(width * 0.025), int(width * 0.16 / max(1, len(AVATAR_ORDER) - 1)))
    total = avatar_w * len(AVATAR_ORDER) + gap * (len(AVATAR_ORDER) - 1)
    start_x = int((width - total) / 2)
    avatar_y = int(height * 0.68)
    for idx, name in enumerate(AVATAR_ORDER):
        is_active = name in active_speakers or ("CLAUDE" in active_speakers and name == "クロード君")
        scale = 1.16 if is_active else 1.0
        aw = int(avatar_w * scale)
        ah = int(avatar_h * scale)
        x = start_x + idx * (avatar_w + gap) - int((aw - avatar_w) / 2)
        float_y = int(10 * (idx % 2) + 8 * (1 if is_active else 0))
        y = avatar_y - int((ah - avatar_h) / 2) - float_y
        bounce = max(8, int(height * 0.012)) if is_active else 0

        def by(value: int) -> str:
            if not bounce:
                return str(value)
            return f"{value}-abs(sin(2*PI*t*2.4))*{bounce}"

        base_color = AVATAR_COLORS.get(name, COLOR_BLUE)
        persona = AVATAR_PERSONAS.get(name, {"face": name[:1], "role": "AI"})
        face = persona["face"]
        role = persona["role"]
        fill = "0x111821" if not is_active else "0x182330"
        head = int(min(aw, ah) * 0.48)
        head_x = x + int((aw - head) / 2)
        head_y = y + int(ah * 0.16)
        neck_w = int(aw * 0.18)
        neck_h = int(ah * 0.08)
        neck_x = x + int((aw - neck_w) / 2)
        neck_y = head_y + head - int(ah * 0.02)
        body_w = int(aw * 0.62)
        body_h = int(ah * 0.24)
        body_x = x + int((aw - body_w) / 2)
        body_y = neck_y + neck_h
        arm_w = int(aw * 0.22)
        arm_h = int(ah * 0.08)
        if is_active:
            filters.append(
                f"drawbox=x={x-26}:y={by(y-26)}:w={aw+52}:h={ah+52}:"
                f"color={base_color}@0.22:t=fill:enable='gte(t,0)'"
            )
        filters.append(f"drawbox=x={x+20}:y={by(y+30)}:w={aw}:h={ah}:color=0x000000@0.18:t=fill")
        filters.append(f"drawbox=x={x + int(aw*0.14)}:y={by(y - int(height*0.018))}:w={int(aw*0.72)}:h=2:color={base_color}@0.38:t=fill")
        filters.append(f"drawbox=x={head_x-14}:y={by(head_y-14)}:w={head+28}:h={head+28}:color={base_color}@0.18:t=fill")
        filters.append(f"drawbox=x={head_x}:y={by(head_y)}:w={head}:h={head}:color=0xF4EFE6@0.92:t=fill")
        filters.append(f"drawbox=x={head_x}:y={by(head_y)}:w={head}:h={head}:color={base_color}@0.95:t=4")
        filters.append(f"drawbox=x={head_x + int(head*0.16)}:y={by(head_y - int(head*0.15))}:w={int(head*0.68)}:h={int(head*0.20)}:color={base_color}@0.86:t=fill")
        filters.append(f"drawbox=x={head_x + int(head*0.08)}:y={by(head_y + int(head*0.10))}:w={int(head*0.18)}:h={int(head*0.18)}:color={base_color}@0.55:t=fill")
        filters.append(f"drawbox=x={head_x + int(head*0.74)}:y={by(head_y + int(head*0.10))}:w={int(head*0.18)}:h={int(head*0.18)}:color={base_color}@0.55:t=fill")
        filters.append(f"drawbox=x={head_x + int(head*0.23)}:y={by(head_y + int(head*0.34))}:w={max(4, int(head*0.10))}:h={max(4, int(head*0.10))}:color={base_color}@0.95:t=fill")
        filters.append(f"drawbox=x={head_x + int(head*0.66)}:y={by(head_y + int(head*0.34))}:w={max(4, int(head*0.10))}:h={max(4, int(head*0.10))}:color={base_color}@0.95:t=fill")
        filters.append(f"drawbox=x={head_x + int(head*0.32)}:y={by(head_y + int(head*0.68))}:w={int(head*0.36)}:h=3:color={base_color}@0.72:t=fill")
        filters.append(f"drawbox=x={neck_x}:y={by(neck_y)}:w={neck_w}:h={neck_h}:color=0xF4EFE6@0.80:t=fill")
        filters.append(f"drawbox=x={body_x}:y={by(body_y)}:w={body_w}:h={body_h}:color={fill}@0.82:t=fill")
        filters.append(f"drawbox=x={body_x}:y={by(body_y)}:w={body_w}:h={body_h}:color={base_color}@0.82:t=3")
        filters.append(f"drawbox=x={body_x - arm_w + 4}:y={by(body_y + int(body_h*0.12))}:w={arm_w}:h={arm_h}:color={base_color}@0.50:t=fill")
        filters.append(f"drawbox=x={body_x + body_w - 4}:y={by(body_y + int(body_h*0.12))}:w={arm_w}:h={arm_h}:color={base_color}@0.50:t=fill")
        filters.append(
            f"drawtext=fontfile='{FONT_BOLD}':text='{_escape(face)}':"
            f"fontsize={max(24, int(head * 0.36))}:fontcolor={base_color}:"
            f"x={head_x}+(%d-text_w)/2:y={by(head_y + int(head * 0.46))}-text_h/2" % head
        )
        filters.append(
            f"drawtext=fontfile='{FONT_BOLD}':text='{_escape(name)}':"
            f"fontsize={max(20, int(height * 0.022))}:fontcolor={COLOR_WHITE}:"
            f"x={x}+(%d-text_w)/2:y={by(y + int(ah * 0.76))}" % aw
        )
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{_escape(role)}':"
            f"fontsize={max(14, int(height * 0.016))}:fontcolor={base_color}:"
            f"x={x}+(%d-text_w)/2:y={by(y + int(ah * 0.90))}" % aw
        )
        filters.append(
            f"drawbox=x={x + int(aw*0.40)}:y={by(y + ah + int(height*0.025))}:"
            f"w={int(aw*0.20)}:h=2:color={base_color}@0.36:t=fill"
        )
    return filters


def _create_meeting_room_clip(out_path, content, duration, width, height, fps, background_video_path: Optional[Path] = None):
    filters = _meeting_room_filters(content, width, height)
    _run_graphic(out_path, COLOR_SUMI, filters, duration, width, height, fps, background_video_path)


def _create_talker_clip(out_path, content, duration, width, height, fps, speaker, background_video_path: Optional[Path] = None):
    speaker = _display_speaker_name(speaker)
    filters = _meeting_room_filters(content, width, height, active_speaker=speaker)
    speaker_size = _fit_font_size([speaker], width, height, base_size=max(30, int(height * 0.038)), min_size=24, max_width_ratio=0.72, max_height_ratio=0.08)
    filters.append(
        f"drawtext=fontfile='{FONT_BOLD}':text='{_escape(speaker)}':"
        f"fontsize={speaker_size}:fontcolor={COLOR_SHINSHU}:"
        f"x=(w-text_w)/2:y={int(height * 0.61)}:"
        f"alpha='0.65+0.35*sin(2*PI*t)'"
    )
    _run_graphic(out_path, COLOR_SUMI, filters, duration, width, height, fps, background_video_path)


def _create_talkers_clip(out_path, content, duration, width, height, fps, speakers, background_video_path: Optional[Path] = None):
    speakers = [_display_speaker_name(speaker) for speaker in (speakers or [])]
    filters = _meeting_room_filters(content, width, height, active_speaker=speakers)
    label = " + ".join(speakers) if speakers else "Multiple speakers"
    label_text = label + " speaking"
    label_size = _fit_font_size([label_text], width, height, base_size=max(30, int(height * 0.038)), min_size=24, max_width_ratio=0.78, max_height_ratio=0.08)
    filters.append(
        f"drawtext=fontfile='{FONT_BOLD}':text='{_escape(label_text)}':"
        f"fontsize={label_size}:fontcolor={COLOR_SHINSHU}:"
        f"x=(w-text_w)/2:y={int(height * 0.61)}:"
        f"alpha='0.65+0.35*sin(2*PI*t)'"
    )
    _run_graphic(out_path, COLOR_SUMI, filters, duration, width, height, fps, background_video_path)


def _create_bar_chart_clip(out_path, content, duration, width, height, fps, background_video_path: Optional[Path] = None):
    """棒グラフ：棒が順番に出現し数値がフェードイン"""
    items = []
    for part in content.split():
        if ":" in part:
            label, val = part.split(":", 1)
            numeric = re.sub(r'[^0-9.]', '', val)
            if numeric:
                items.append((label, float(numeric), val))
            else:
                state_scores = {
                    "増": 100,
                    "重い": 100,
                    "即時影響": 100,
                    "残": 78,
                    "横ばい": 56,
                    "薄い": 34,
                    "減": 24,
                }
                items.append((label, state_scores.get(val, 64), val))

    if not items:
        _create_dark_text_clip(out_path, content, duration, width, height, fps, background_video_path)
        return

    max_val = max(v for _, v, _ in items) or 1
    bar_width = 140
    bar_max_height = int(height * 0.38)
    x_start = int(width * 0.12)
    bar_spacing = int((width * 0.76) / max(len(items), 1))
    base_y = int(height * 0.76)

    filters = [_dark_bg_vf(width, height)]
    colors = ["0x4a7c59", COLOR_SHINSHU, "0x2a6b9c", "0xd4a017"]

    title_lines = _wrap_visual_lines([content], max_units=28 if height > width else 46, max_lines=2)
    title_size = _fit_font_size(title_lines, width, height, base_size=52, min_size=28, max_width_ratio=0.86, max_height_ratio=0.12)
    for title_idx, title_line in enumerate(title_lines):
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{_escape(title_line)}':"
            f"fontsize={title_size}:fontcolor={COLOR_WHITE}:"
            f"x=(w-text_w)/2:y={int(height * 0.10) + title_idx * int(title_size * 1.25)}:"
            f"alpha='min(1,t/0.4)'"
        )

    for idx, (label, val, val_str) in enumerate(items):
        bar_h = max(20, int(bar_max_height * val / max_val))
        x = x_start + idx * bar_spacing
        color = colors[idx % len(colors)]
        bar_delay = round(0.5 + idx * 0.9, 2)
        val_delay = round(bar_delay + 0.5, 2)

        # 棒を4段階で伸ばす（下から上へグロー）
        steps = 4
        for s in range(1, steps + 1):
            ph = max(1, int(bar_h * s / steps))
            py = base_y - ph
            td = round(bar_delay + (s - 1) * 0.12, 2)
            filters.append(
                f"drawbox=x={x}:y={py}:w={bar_width}:h={ph}:"
                f"color={color}:t=fill:enable='gte(t,{td})'"
            )
        y_top = base_y - bar_h
        # ラベル（棒と同時）
        label_lines = _wrap_visual_lines([label], max_units=8 if len(items) >= 3 else 12, max_lines=2)
        label_size = _fit_font_size(label_lines, bar_width * 2, height, base_size=42, min_size=22, max_width_ratio=0.82, max_height_ratio=0.07)
        for label_idx, label_line in enumerate(label_lines):
            filters.append(
                f"drawtext=fontfile='{FONT_FILE}':text='{_escape(label_line)}':"
                f"fontsize={label_size}:fontcolor={COLOR_WHITE}:"
                f"x={x + bar_width // 2}-text_w/2:y={base_y + 22 + label_idx * int(label_size * 1.2)}:"
                f"enable='gte(t,{bar_delay})':alpha='min(1,(t-{bar_delay})/0.3)'"
            )
        # 数値（棒の後）
        val_size = _fit_font_size([val_str], bar_width * 2, height, base_size=50, min_size=22, max_width_ratio=0.90, max_height_ratio=0.05)
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{_escape(val_str)}':"
            f"fontsize={val_size}:fontcolor={color}:"
            f"x={x + bar_width // 2}-text_w/2:y={y_top - int(val_size * 1.35)}:"
            f"enable='gte(t,{val_delay})':alpha='min(1,(t-{val_delay})/0.3)'"
        )

    _run_graphic(out_path, COLOR_SUMI, filters, duration, width, height, fps, background_video_path)


def _create_flow_clip(out_path, content, duration, width, height, fps, background_video_path: Optional[Path] = None):
    """フローチャート：ボックスと矢印が順次出現"""
    steps = [s.strip() for s in re.split(r'[→\-\>]', content) if s.strip()]

    filters = [_dark_bg_vf(width, height)]
    y_start = int(height * 0.22)
    step_height = int(height * 0.11)
    box_w = int(width * 0.78)
    box_x = int(width * 0.11)
    gap = 72  # ボックス間の余白
    step_interval = 1.0  # 各ステップの出現間隔（秒）

    for i, step in enumerate(steps[:5]):
        y = y_start + i * (step_height + gap)
        box_delay = round(i * step_interval, 2)
        text_delay = round(box_delay + 0.15, 2)
        arrow_delay = round(box_delay + 0.6, 2)

        text_color = COLOR_SHINSHU if i == len(steps) - 1 else COLOR_WHITE
        box_color = f"{COLOR_SHINSHU}@0.25" if i == len(steps) - 1 else f"{COLOR_WASHI}@0.12"
        border_color = f"{COLOR_SHINSHU}@0.7" if i == len(steps) - 1 else f"{COLOR_WASHI}@0.45"

        # ボックス背景
        filters.append(
            f"drawbox=x={box_x}:y={y}:w={box_w}:h={step_height}:"
            f"color={box_color}:t=fill:"
            f"enable='gte(t,{box_delay})'"
        )
        # ボックス枠
        filters.append(
            f"drawbox=x={box_x}:y={y}:w={box_w}:h={step_height}:"
            f"color={border_color}:t=3:"
            f"enable='gte(t,{box_delay})'"
        )
        step_lines = _wrap_visual_lines([step], max_units=22 if height > width else 36, max_lines=2)
        step_size = _fit_font_size(step_lines, box_w, step_height, base_size=48, min_size=24, max_width_ratio=0.84, max_height_ratio=0.82)
        step_line_height = int(step_size * 1.12)
        step_text_y = y + int((step_height - step_line_height * len(step_lines)) / 2)
        for step_idx, step_line in enumerate(step_lines):
            filters.append(
                f"drawtext=fontfile='{FONT_FILE}':text='{_escape(step_line)}':"
                f"fontsize={step_size}:fontcolor={text_color}:"
                f"x=(w-text_w)/2:y={step_text_y + step_idx * step_line_height}:"
                f"enable='gte(t,{text_delay})':alpha='min(1,(t-{text_delay})/0.3)'"
            )
        # 矢印（最終ステップの後ろには出さない）
        if i < len(steps) - 1:
            arrow_y = y + step_height + 8
            filters.append(
                f"drawtext=fontfile='{FONT_FILE}':text='↓':"
                f"fontsize=58:fontcolor={COLOR_SHINSHU}:"
                f"x=(w-text_w)/2:y={arrow_y}:"
                f"enable='gte(t,{arrow_delay})':alpha='min(1,(t-{arrow_delay})/0.25)'"
            )

    _run_graphic(out_path, COLOR_SUMI, filters, duration, width, height, fps, background_video_path)


def _create_title_clip(out_path, content, duration, width, height, fps, background_video_path: Optional[Path] = None):
    """タイトル：大見出し → サブタイトルの順にフェードイン"""
    lines = content.replace("\\n", "\n").split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    wrapped = _wrap_visual_lines_with_meta(lines, max_units=18 if height > width else 30, max_lines=6)
    lines = [line for line, _, _ in wrapped]

    filters = [_dark_bg_vf(width, height)]
    y_center = height * 0.42
    first_size = _fit_font_size(lines[:1], width, height, base_size=96, min_size=46, max_width_ratio=0.86, max_height_ratio=0.13)
    other_size = _fit_font_size(lines[1:] or lines[:1], width, height, base_size=68, min_size=34, max_width_ratio=0.86, max_height_ratio=0.22)
    line_height = int(max(first_size, other_size) * 1.28)

    for i, (line, raw_idx, _) in enumerate(wrapped):
        delay = round(i * 0.55, 2)
        y = int(y_center + (i - len(lines) / 2) * line_height)
        if raw_idx == 0:
            size = first_size
            color = COLOR_SHINSHU
        else:
            size = other_size
            color = COLOR_WHITE
        filters.append(
            f"drawtext=fontfile='{FONT_FILE}':text='{_escape(line)}':"
            f"fontsize={size}:fontcolor={color}:"
            f"x=(w-text_w)/2:y={y}:"
            f"box=1:boxcolor={COLOR_SUMI}@0.75:boxborderw=28:"
            f"enable='gte(t,{delay})':alpha='min(1,(t-{delay})/0.45)'"
        )

    _run_graphic(out_path, COLOR_SUMI, filters, duration, width, height, fps, background_video_path)


def _create_sepia_clip(out_path, content, duration, width, height, fps, background_video_path: Optional[Path] = None):
    """セピア調アニメ背景 + テキストフェードイン"""
    filters = [_sepia_bg_vf(width, height)]

    if content:
        lines = content.replace("\\n", "\n").split("\n")
        lines = [l.strip() for l in lines if l.strip()]
        lines = _wrap_visual_lines(lines, max_units=24 if height > width else 38, max_lines=5)
        n = len(lines)
        size = _fit_font_size(lines, width, height, base_size=56, min_size=32, max_width_ratio=0.82, max_height_ratio=0.30)
        line_height = int(size * 1.35)
        y_start = int(height * 0.5 - (n * line_height) / 2)
        for i, line in enumerate(lines):
            delay = round(i * 0.5, 2)
            y = y_start + i * line_height
            filters.append(
                f"drawtext=fontfile='{FONT_FILE}':text='{_escape(line)}':"
                f"fontsize={size}:fontcolor={COLOR_WHITE}:"
                f"x=(w-text_w)/2:y={y}:"
                f"box=1:boxcolor={COLOR_SUMI}@0.55:boxborderw=16:"
                f"enable='gte(t,{delay})':alpha='min(1,(t-{delay})/0.4)'"
            )

    _run_graphic(out_path, "0x8B7355", filters, duration, width, height, fps, background_video_path)
