import os
import re
from pathlib import Path
from typing import List, Dict

FONT = os.getenv("SUBTITLE_FONT", "Noto Serif CJK JP")
DEFAULT_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "72"))
DEFAULT_WRAP_CHARS = int(os.getenv("SUBTITLE_WRAP_CHARS", "14"))
DEFAULT_MAX_LINES = int(os.getenv("SUBTITLE_MAX_LINES", "3"))
DEFAULT_POSITION_FROM_BOTTOM_PCT = float(os.getenv("SUBTITLE_POSITION_FROM_BOTTOM_PCT", "33"))
PRIMARY_COLOR = os.getenv("SUBTITLE_PRIMARY_COLOR", "&H00E6EFF4&")
OUTLINE_COLOR = os.getenv("SUBTITLE_OUTLINE_COLOR", "&H0014171A&")


def _ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        s += 1
        cs -= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _escape_ass(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\n", r"\N")


def _clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _split_long_token(token: str, max_chars: int) -> List[str]:
    token = token.strip()
    if not token:
        return []
    return [token[i:i + max_chars] for i in range(0, len(token), max_chars)]


def _split_phrase_units(text: str) -> List[str]:
    """日本語字幕を自然な文節に近い位置で折り返すための小さな単位へ分けます。"""
    text = _clean_text(text)
    if not text:
        return []

    units: List[str] = []
    for paragraph in text.split("\n"):
        p = paragraph.strip()
        if not p:
            continue

        # 句読点・記号の直後でまず区切る
        pieces = re.findall(r"[^、。！？!?；;：:\n]+[、。！？!?；;：:]?", p)
        if not pieces:
            pieces = [p]

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue

            # 長い場合は助詞の後ろでも軽く区切る
            sub = re.split(
                r"(?<=[はがをにへとでやもからまでよりの])",
                piece
            )
            for item in sub:
                item = item.strip()
                if item:
                    units.append(item)
    return units


def wrap_japanese_subtitle(text: str, max_chars: int = DEFAULT_WRAP_CHARS) -> List[str]:
    """1行が長くなりすぎないように、文節寄りで字幕を折り返します。"""
    max_chars = max(8, min(28, int(max_chars or DEFAULT_WRAP_CHARS)))
    units = _split_phrase_units(text)

    lines: List[str] = []
    current = ""

    for unit in units:
        unit = unit.strip()
        if not unit:
            continue

        if len(unit) > max_chars:
            if current:
                lines.append(current)
                current = ""
            lines.extend(_split_long_token(unit, max_chars))
            continue

        if not current:
            current = unit
        elif len(current + unit) <= max_chars:
            current += unit
        else:
            lines.append(current)
            current = unit

    if current:
        lines.append(current)

    return [x.strip() for x in lines if x.strip()]


def _chunk_lines(lines: List[str], max_lines: int) -> List[List[str]]:
    max_lines = max(1, min(5, int(max_lines or DEFAULT_MAX_LINES)))
    if not lines:
        return [[""]]
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]


def _scene_subtitle_events(scene: Dict, max_chars: int, max_lines: int):
    """長い字幕は1シーン内で複数イベントに分割して、画面からはみ出さないようにします。"""
    start = float(scene.get("actual_start", scene["start"]))
    end = float(scene.get("actual_end", scene["end"]))
    duration = max(0.1, end - start)

    text = scene.get("subtitle") or scene.get("narration", "")
    lines = wrap_japanese_subtitle(text, max_chars=max_chars)
    chunks = _chunk_lines(lines, max_lines=max_lines)

    per = duration / max(1, len(chunks))
    events = []
    for idx, chunk in enumerate(chunks):
        ev_start = start + per * idx
        ev_end = start + per * (idx + 1)
        if idx == len(chunks) - 1:
            ev_end = end
        events.append((ev_start, ev_end, "\n".join(chunk)))
    return events


def write_ass_subtitles(
    scenes: List[Dict],
    out_path: Path,
    width: int,
    height: int,
    font_size: int | None = None,
    wrap_chars: int | None = None,
    max_lines: int | None = None,
    position_from_bottom_pct: float | None = None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    size = int(font_size or DEFAULT_FONT_SIZE)
    title_size = size + 10
    wrap_chars = int(wrap_chars or DEFAULT_WRAP_CHARS)
    max_lines = int(max_lines or DEFAULT_MAX_LINES)

    pct = float(position_from_bottom_pct if position_from_bottom_pct is not None else DEFAULT_POSITION_FROM_BOTTOM_PCT)
    pct = max(6.0, min(45.0, pct))
    margin_v = int(height * pct / 100.0)

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},{size},{PRIMARY_COLOR},&H000000FF,{OUTLINE_COLOR},&H80000000,0,0,0,0,100,100,0,0,1,4,0,2,90,90,{margin_v},1
Style: Title,{FONT},{title_size},{PRIMARY_COLOR},&H000000FF,{OUTLINE_COLOR},&H80000000,1,0,0,0,100,100,0,0,1,4,0,5,90,90,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for scene in scenes:
        for ev_start, ev_end, ev_text in _scene_subtitle_events(scene, wrap_chars, max_lines):
            start = _ass_time(ev_start)
            end = _ass_time(ev_end)
            text = _escape_ass(ev_text)
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def write_srt_subtitles(
    scenes: List[Dict],
    out_path: Path,
    wrap_chars: int | None = None,
    max_lines: int | None = None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrap_chars = int(wrap_chars or DEFAULT_WRAP_CHARS)
    max_lines = int(max_lines or DEFAULT_MAX_LINES)

    blocks = []
    idx = 1
    for scene in scenes:
        for ev_start, ev_end, ev_text in _scene_subtitle_events(scene, wrap_chars, max_lines):
            blocks.append(
                f"{idx}\n{_srt_time(ev_start)} --> {_srt_time(ev_end)}\n{ev_text}\n"
            )
            idx += 1

    out_path.write_text("\n".join(blocks), encoding="utf-8")
    return out_path
