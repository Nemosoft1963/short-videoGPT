import os
import re
from pathlib import Path
from typing import Dict, List, Optional


FONT = os.getenv("SUBTITLE_FONT", "Noto Serif CJK JP")
DEFAULT_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "72"))
DEFAULT_WRAP_CHARS = int(os.getenv("SUBTITLE_WRAP_CHARS", "14"))
DEFAULT_MAX_LINES = int(os.getenv("SUBTITLE_MAX_LINES", "3"))
DEFAULT_POSITION_FROM_BOTTOM_PCT = float(os.getenv("SUBTITLE_POSITION_FROM_BOTTOM_PCT", "40"))

SUBTITLE_MIN_EVENT_SECONDS = float(os.getenv("SUBTITLE_MIN_EVENT_SECONDS", "0.75"))
SUBTITLE_MAX_EVENT_SECONDS = float(os.getenv("SUBTITLE_MAX_EVENT_SECONDS", "2.6"))
SUBTITLE_CHARS_PER_SECOND = float(os.getenv("SUBTITLE_CHARS_PER_SECOND", "11.5"))
SUBTITLE_MAX_TAIL_HOLD_SECONDS = float(os.getenv("SUBTITLE_MAX_TAIL_HOLD_SECONDS", "0.45"))
TYPEWRITER_RATIO = float(os.getenv("SUBTITLE_TYPEWRITER_RATIO", "0.38"))

COLOR_SUMI = "&H00141714&"
COLOR_WASHI = "&H00E6EFF4&"
COLOR_BG = "&H40141714&"

PRIMARY_COLOR = os.getenv("SUBTITLE_PRIMARY_COLOR", COLOR_WASHI)
OUTLINE_COLOR = os.getenv("SUBTITLE_OUTLINE_COLOR", COLOR_SUMI)


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
    text = _clean_text(text)
    if not text:
        return []
    units: List[str] = []
    for paragraph in text.split("\n"):
        p = paragraph.strip()
        if not p:
            continue
        pieces = re.findall(r"[^。、！？!?・\n]+[。、！？!?・]?", p)
        if not pieces:
            pieces = [p]
        for piece in pieces:
            piece = piece.strip()
            if piece:
                units.append(piece)
    return units


def wrap_japanese_subtitle(text: str, max_chars: int = DEFAULT_WRAP_CHARS) -> List[str]:
    max_chars = max(8, min(28, int(max_chars or DEFAULT_WRAP_CHARS)))
    units = _split_phrase_units(text)
    lines: List[str] = []
    current = ""
    for unit in units:
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
    return [line.strip() for line in lines if line.strip()]


def _chunk_lines(lines: List[str], max_lines: int) -> List[List[str]]:
    max_lines = max(1, min(5, int(max_lines or DEFAULT_MAX_LINES)))
    if not lines:
        return [[""]]
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]


def _is_graphic_scene(scene: Dict) -> bool:
    visual = scene.get("visual_prompt", "")
    return "[graphic" in visual.lower()


def _make_typewriter_text(text: str, duration_ms: int, char_fracs: list = None, alignment: int = 2) -> str:
    segments = text.split(r"\N")
    tokens: list[str] = []
    for si, seg in enumerate(segments):
        tokens.extend(list(seg))
        if si < len(segments) - 1:
            tokens.append(r"\N")

    printable = [token for token in tokens if token != r"\N"]
    n = len(printable)
    if n == 0:
        return text

    if char_fracs and len(char_fracs) >= n:
        frac_list = char_fracs[:n]
    else:
        frac_list = [i / n for i in range(n)]

    result = f"{{\\an{alignment}}}"
    pi = 0
    for token in tokens:
        if token == r"\N":
            result += r"\N"
        else:
            start_ms = int(frac_list[pi] * duration_ms)
            result += f"{{\\alpha&HFF&\\t({start_ms},{start_ms + 1},\\alpha&H00&)}}{token}"
            pi += 1
    return result


def _map_fracs_to_chars(mora_fracs: list, n_chars: int) -> list:
    if not mora_fracs or n_chars <= 0:
        return [i / max(n_chars, 1) for i in range(n_chars)]
    n = len(mora_fracs)
    return [mora_fracs[min(round(i / n_chars * n), n - 1)] for i in range(n_chars)]


def _subtitle_durations(chunks: List[List[str]], available: float) -> List[float]:
    weights = [max(1, len("".join(chunk))) for chunk in chunks]
    total_weight = max(1, sum(weights))
    desired = [
        max(
            SUBTITLE_MIN_EVENT_SECONDS,
            min(SUBTITLE_MAX_EVENT_SECONDS, weight / max(SUBTITLE_CHARS_PER_SECOND, 1.0)),
        )
        for weight in weights
    ]
    total_desired = sum(desired)
    if total_desired > available:
        return [available * (weight / total_weight) for weight in weights]
    # Use the whole scene. Previously the spare time was capped, so subtitles
    # vanished several seconds before the next scene and left a blank interval.
    spare = available - total_desired
    return [duration + spare * (weight / total_weight) for duration, weight in zip(desired, weights)]


def _scene_subtitle_events(
    scene: Dict,
    max_chars: int,
    max_lines: int,
    typewriter: bool = True,
    height: int = 1920,
    alignment: int = 2,
):
    start = float(scene.get("actual_start", scene["start"]))
    end = float(scene.get("actual_end", scene["end"]))

    text = scene.get("subtitle", "")
    lines = wrap_japanese_subtitle(text, max_chars=max_chars)
    if not lines:
        return []
    chunks = _chunk_lines(lines, max_lines=max_lines)

    # Keep the final subtitle visible through any padded/held tail of the scene.
    speech_end = end
    available = max(0.1, speech_end - start)
    durations = _subtitle_durations(chunks, available)

    is_graphic = _is_graphic_scene(scene)
    mora_fracs = scene.get("_mora_fracs", [])

    events = []
    cursor = start
    for idx, chunk in enumerate(chunks):
        ev_start = cursor
        ev_end = min(speech_end, ev_start + max(0.1, durations[idx]))
        cursor = ev_end
        if ev_end <= ev_start + 0.03:
            continue

        ev_text = "\n".join(chunk)
        escaped = _escape_ass(ev_text)
        event_duration = max(0.1, ev_end - ev_start)
        typing_ms = int(event_duration * TYPEWRITER_RATIO * 1000)

        if typewriter:
            printable_count = len(escaped.replace(r"\N", ""))
            if printable_count > 0:
                chunk_frac_start = max(0.0, (ev_start - start) / available)
                chunk_frac_end = min(1.0, (ev_end - start) / available)
                chunk_mora = [
                    (f - chunk_frac_start) / max(chunk_frac_end - chunk_frac_start, 1e-6)
                    for f in mora_fracs
                    if chunk_frac_start <= f <= chunk_frac_end
                ] if mora_fracs else []
                char_fracs = _map_fracs_to_chars(chunk_mora, printable_count)
                ass_text = _make_typewriter_text(escaped, typing_ms, char_fracs, alignment=alignment)
            else:
                ass_text = escaped
        else:
            ass_text = escaped

        style = "Graphic" if is_graphic else "Default"
        events.append((ev_start, ev_end, ass_text, style))

    return events


def write_ass_subtitles(
    scenes: List[Dict],
    out_path: Path,
    width: int,
    height: int,
    font_size: Optional[int] = None,
    wrap_chars: Optional[int] = None,
    max_lines: Optional[int] = None,
    position_from_bottom_pct: Optional[float] = None,
    typewriter: bool = True,
    layout: str = "default",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    size = int(font_size or DEFAULT_FONT_SIZE)
    max_lines = int(max_lines or DEFAULT_MAX_LINES)

    explain_left = layout == "explain_left" and width > height
    margin_lr = int(width * 0.48) if explain_left else 120
    char_px = size + 2
    screen_max_chars = max(8, int((width - margin_lr) / char_px))
    wrap_chars = min(int(wrap_chars or DEFAULT_WRAP_CHARS), screen_max_chars)

    pct = float(position_from_bottom_pct if position_from_bottom_pct is not None else DEFAULT_POSITION_FROM_BOTTOM_PCT)
    pct = max(6.0, min(55.0, pct))
    margin_v_bottom = int(height * pct / 100.0)
    alignment = 4 if explain_left else 2
    margin_l = max(60, int(width * 0.045)) if explain_left else 60
    margin_r = max(60, int(width * 0.45)) if explain_left else 60
    margin_v = max(40, int(height * 0.08)) if explain_left else margin_v_bottom

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},{size},{PRIMARY_COLOR},&H000000FF,{OUTLINE_COLOR},{COLOR_BG},0,0,0,0,100,100,1,0,3,5,1,{alignment},{margin_l},{margin_r},{margin_v},1
Style: Graphic,{FONT},{size},{PRIMARY_COLOR},&H000000FF,{OUTLINE_COLOR},{COLOR_BG},1,0,0,0,100,100,1,0,3,5,1,{alignment},{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines_out = [header]
    for scene in scenes:
        for ev_start, ev_end, ev_text, style in _scene_subtitle_events(
            scene, wrap_chars, max_lines, typewriter=typewriter, height=height, alignment=alignment
        ):
            s = _ass_time(ev_start)
            e = _ass_time(ev_end)
            lines_out.append(f"Dialogue: 0,{s},{e},{style},,0,0,0,,{ev_text}\n")

    out_path.write_text("".join(lines_out), encoding="utf-8")
    return out_path


def write_srt_subtitles(
    scenes: List[Dict],
    out_path: Path,
    wrap_chars: Optional[int] = None,
    max_lines: Optional[int] = None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrap_chars = int(wrap_chars or DEFAULT_WRAP_CHARS)
    max_lines = int(max_lines or DEFAULT_MAX_LINES)

    blocks = []
    idx = 1
    for scene in scenes:
        for ev_start, ev_end, ev_text, _ in _scene_subtitle_events(
            scene, wrap_chars, max_lines, typewriter=False
        ):
            blocks.append(
                f"{idx}\n{_srt_time(ev_start)} --> {_srt_time(ev_end)}\n{ev_text}\n"
            )
            idx += 1

    out_path.write_text("\n".join(blocks), encoding="utf-8")
    return out_path
