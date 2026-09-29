import os
import re
from typing import Dict, List

from services.voice_profiles import normalize_speaker

NEGATIVE = "No text, no letters, no subtitles, no logos, no watermark, no anime, no cartoon, no 3D render, no neon colors, no colorful effects, no smiling business people, no western shop, no modern luxury office."

STYLE_PREFIXES = {
    "serious_documentary": "Photorealistic cinematic documentary footage, natural lighting, shallow depth of field, subtle camera movement.",
    "small_business_awareness": "Photorealistic Japanese small business documentary footage, warm natural light, authentic environment.",
    "tax_issue": "Photorealistic Japanese documentary footage, serious atmosphere, muted natural colors, authentic settings.",
    "recruiting": "Photorealistic Japanese workplace documentary footage, calm professional atmosphere, natural lighting.",
    "product_intro": "Photorealistic clean product footage, simple background, professional lighting, minimal.",
}

# シーンキーワードから映像プロンプトを自動生成するマッピング
VISUAL_KEYWORD_MAP = [
    # キーワード → 映像プロンプト
    (["子猫", "猫", "kitten", "cat"], 
     "A cute small kitten sitting on a traditional Japanese tatami floor, soft warm sunlight through shoji screen, gentle calm atmosphere"),
    (["和菓子", "菓子", "店内", "wagashi"],
     "Interior of an old traditional Japanese wagashi confectionery shop, wooden shelves with traditional sweets, warm dusty light through small windows, nostalgic atmosphere"),
    (["店舗", "店", "外観", "shop", "storefront"],
     "Old traditional Japanese shop exterior, wooden storefront, aged signboard, quiet street, morning light, sepia toned atmosphere"),
    (["書類", "帳簿", "ledger", "document", "税"],
     "Close-up of aged Japanese accounting ledger on wooden desk, calculator, tax documents, hands of elderly shop owner, warm desk lamp"),
    (["銀行", "融資", "loan", "bank"],
     "Quiet Japanese bank consultation counter, serious atmosphere, loan application documents on desk, formal setting"),
    (["暗", "墨", "dark", "black", "拒絶"],
     "Dark traditional Japanese interior, deep shadows, single shaft of light, heavy oppressive atmosphere, wooden beams"),
    (["和紙", "ベージュ", "washi", "paper"],
     "Close-up of traditional Japanese washi paper texture, warm beige surface, subtle fiber details, soft diffused light"),
    (["看板", "閉店", "廃業", "signboard"],
     "Closed traditional Japanese shop at dusk, faded signboard, shuttered storefront, empty street, melancholic atmosphere"),
    (["電卓", "計算", "calculator", "数字"],
     "Close-up of vintage calculator on wooden desk, accounting papers, pen, hands working through financial documents"),
    (["夕暮れ", "夜", "evening", "night"],
     "Traditional Japanese shopping street at evening, soft street lights, quiet atmosphere, few pedestrians, melancholic mood"),
]

DEFAULT_VISUALS = [
    "Old traditional Japanese shop exterior in morning light, wooden storefront, quiet street, cinematic documentary style",
    "Close-up of aged accounting ledger on wooden desk, calculator, tax documents, warm lamp light",
    "Quiet Japanese bank consultation room, formal documents on desk, serious atmosphere",
    "Close-up of traditional Japanese washi paper with handwritten numbers, warm natural light",
    "Dark traditional Japanese interior, deep shadows, single shaft of light, heavy atmosphere",
    "Traditional Japanese shop at dusk, faded signboard, shuttered storefront, empty street",
    "Close-up of vintage calculator and tax documents on wooden desk, elderly hands",
    "Quiet traditional Japanese street at evening, soft lights, melancholic atmosphere",
]

SPEAKER_LINE_RE = re.compile(r"^(?:ナレーション|Narration)\s*[（(]\s*([^）)]+)\s*[）)]\s*[:：]\s*(.+)$", re.IGNORECASE)
CHARACTER_LINE_RE = re.compile(r"^([A-Za-z0-9_ぁ-んァ-ヶ一-龠々ー]+)\s*[:：]\s*(.+)$")
KNOWN_SPEAKERS = {
    "GMN", "YT", "META", "GPT", "GROCK", "Grock", "CLAUDE", "クロード", "クロード君",
    "分析官K", "分析官Ｋ", "調査員S", "調査員Ｓ", "少佐", "Major", "MAJOR",
    "Narrator", "Narration", "NARRATION", "ナレーション", "ナレーター",
    "ドライバー", "社長", "銀行担当者", "父親", "子ども",
    "Driver", "President", "Banker", "Father", "ChildBoy",
    "K", "S", "ANALYST_K", "INVESTIGATOR_S",
    "ＧＭＮ", "ＹＴ", "ＭＥＴＡ", "ＧＰＴ",
}
INSERT_TAG_RE = re.compile(r"\[insert\s*:\s*([^\]\s]+)(?:\s+([^\]]+))?\]", re.IGNORECASE)
BGM_TAG_RE = re.compile(r"\[bgm\s*:\s*([^\]]+)\]", re.IGNORECASE)
FLASH_TAG_RE = re.compile(r"\[flash\s*:\s*([^:\]]+)(?:\s*:\s*([^\]]+))?\]", re.IGNORECASE)
MOTOKO_TAG_RE = re.compile(r"\[motoko\s*:\s*([^\]]+)\]", re.IGNORECASE)
OVERLAY_GRAPHIC_TAG_RE = re.compile(r"\[overlay\s*:\s*(graphic(?::[^\]]+)?)\]", re.IGNORECASE)
GRAPHIC_TAG_RE = re.compile(r"\[graphic(?::[^\]]+)?\]", re.IGNORECASE)
VISUAL_LABEL_PREFIX_RE = re.compile(r"^(?:映像|visual)\s*[:：]\s*", re.IGNORECASE)
FLASH_PRESETS = {
    "red_impact": ("警告", "cinematic red impact warning flash"),
}
CITE_RE = re.compile(r"\s*\[cite\s*:\s*\d+\]\s*", re.IGNORECASE)
MARKDOWN_RULE_RE = re.compile(r"^\s*[-*_]{3,}\s*$")
PHF_FLASH_DURATION = float(os.getenv("PHF_FLASH_DURATION", "0.7"))
SHORT_SILENT_END_CARD_SECONDS = float(os.getenv("SHORT_SILENT_END_CARD_SECONDS", "2.8"))
FIXED_SHORT_BODY_DURATIONS = {
    "fixed_44": 43,
    "fixed_57": 56,
}


def _fixed_short_body_duration(project: Dict) -> int | None:
    if project.get("format", "short_vertical") != "short_vertical":
        return None
    return FIXED_SHORT_BODY_DURATIONS.get(project.get("short_timing_mode", "fixed_57"))


def _is_standard_script_unbounded(project: Dict) -> bool:
    return (
        project.get("format") == "standard_landscape"
        and project.get("standard_timing_mode") == "script_unbounded"
    )


def _parse_insert_tag(raw: str) -> tuple[str, dict]:
    raw = (raw or "").strip()
    if re.match(r"https?://", raw, re.IGNORECASE):
        options = {}
        match = re.match(r"^(https?://.+):(warning|alert|danger|news|center)$", raw, re.IGNORECASE)
        if match:
            raw = match.group(1)
            options["insert_layer"] = "warning"
        return raw, options

    parts = [p.strip() for p in re.split(r"[:|,]", raw or "") if p.strip()]
    if not parts:
        return "", {}
    insert_id = parts[0]
    flags = {p.lower() for p in parts[1:]}
    options = {}
    if flags & {"warning", "alert", "danger", "news", "center", "警告"}:
        options["insert_layer"] = "warning"
    return insert_id, options


def _strip_insert_tag(line: str, current_insert_id: str | None, current_insert_options: dict | None = None) -> tuple[str, str | None, dict]:
    current_insert_options = dict(current_insert_options or {})
    matches = list(INSERT_TAG_RE.finditer(line))
    insert_id = current_insert_id
    for match in matches:
        parsed_id, parsed_options = _parse_insert_tag(match.group(1))
        if parsed_id and not insert_id:
            insert_id = parsed_id
        current_insert_options.update(parsed_options)
        if match.group(2):
            _, trailing_options = _parse_insert_tag(f"placeholder:{match.group(2)}")
            current_insert_options.update(trailing_options)
    cleaned = INSERT_TAG_RE.sub("", line).strip()
    if cleaned.lower() in ("insert:", "insert："):
        cleaned = ""
    if cleaned.startswith(("挿入:", "挿入：")) and not cleaned.replace("挿入", "", 1).strip(" :："):
        cleaned = ""
    return cleaned, insert_id, current_insert_options


def _parse_bgm_value(raw: str) -> str:
    value = (raw or "").strip().strip('"').strip("'")
    value = value.replace("\\", "/").split("/")[-1]
    if value.lower() in {"", "none", "off", "なし", "無し"}:
        return ""
    return value


def _strip_bgm_tag(line: str, current_bgm: str | None = None) -> tuple[str, str | None]:
    bgm = current_bgm

    def replace_tag(match):
        nonlocal bgm
        value = _parse_bgm_value(match.group(1))
        bgm = value if value else None
        return ""

    cleaned = BGM_TAG_RE.sub(replace_tag, line).strip()
    for label in ("BGM:", "BGM：", "bgm:", "bgm："):
        if cleaned.startswith(label):
            bgm = _parse_bgm_value(cleaned[len(label):])
            cleaned = ""
            break
    return cleaned, bgm


def _is_bgm_directive_only(line: str) -> bool:
    cleaned, bgm = _strip_bgm_tag(line, None)
    has_directive = bool(BGM_TAG_RE.search(line or "")) or (line or "").strip().startswith(("BGM:", "BGM：", "bgm:", "bgm："))
    return has_directive and not cleaned.strip()


def _strip_motoko_overlay_tags(line: str, options: dict) -> tuple[str, dict]:
    options = dict(options or {})
    overlay_tag_matched = False
    for match in MOTOKO_TAG_RE.finditer(line or ""):
        tokens = {part.strip().lower() for part in re.split(r"[:|,\s]+", match.group(1) or "") if part.strip()}
        options["motoko_lipsync"] = True
        if tokens & {"fullscreen", "full", "scene"}:
            options["lipsync_display_mode"] = "full"
        if tokens & {"bottom", "lower"}:
            options["lipsync_display_mode"] = "bottom"
        if tokens & {"explain_right", "explain", "right", "lecturer"}:
            options["lipsync_display_mode"] = "explain_right"
        if tokens & {"anime", "real"}:
            options["lipsync_source_set"] = "real" if "real" in tokens else "anime"
        if tokens & {"image", "video", "auto"}:
            if "video" in tokens:
                options["lipsync_source_mode"] = "video"
            elif "auto" in tokens:
                options["lipsync_source_mode"] = "auto"
            else:
                options["lipsync_source_mode"] = "image"

    def replace_overlay(match):
        nonlocal overlay_tag_matched
        overlay_tag_matched = True
        tag = (match.group(1) or "graphic").strip()
        if tag.lower() == "graphic:*":
            options["graphic_overlay_wildcard"] = True
        else:
            options["graphic_overlay_prompt"] = f"[{tag}]"
        return ""

    cleaned = OVERLAY_GRAPHIC_TAG_RE.sub(replace_overlay, MOTOKO_TAG_RE.sub("", line or "")).strip()
    if overlay_tag_matched and options.get("graphic_overlay_prompt") and cleaned:
        options["graphic_overlay_prompt"] = _sanitize_graphic_overlay_prompt(f"{options['graphic_overlay_prompt']} {cleaned}".strip())
        cleaned = ""
    return cleaned, options


def _sanitize_graphic_overlay_prompt(raw: str) -> str:
    prompt = VISUAL_LABEL_PREFIX_RE.sub("", (raw or "").strip())
    match = GRAPHIC_TAG_RE.search(prompt)
    if not match:
        return prompt
    tag = match.group(0)
    body = prompt[match.end():].strip()
    body = VISUAL_LABEL_PREFIX_RE.sub("", body)
    body = GRAPHIC_TAG_RE.sub("", body).strip()
    return f"{tag} {body}".strip()


def _clean_spoken_text(text: str) -> str:
    return CITE_RE.sub("", (text or "")).strip()


def _has_script_content(block: str) -> bool:
    lowered = (block or "").lower()
    if "[graphic" in lowered or "[insert" in lowered or "[flash" in lowered or "[bgm" in lowered:
        return True
    markers = ("映像", "ナレーション", "字幕", "BGM:", "BGM：", "visual:", "narration:", "subtitle:", "bgm:", "Visual:", "Narration:", "Subtitle:")
    if any(marker in block for marker in markers):
        return True
    for line in (block or "").splitlines():
        match = CHARACTER_LINE_RE.match(line.strip())
        if match and normalize_speaker(match.group(1)) in {normalize_speaker(s) for s in KNOWN_SPEAKERS}:
            return True
    return False


def _match_visual_prompt(text: str) -> str:
    """テキストからキーワードマッチングで映像プロンプトを返す"""
    for keywords, prompt in VISUAL_KEYWORD_MAP:
        if any(kw in text for kw in keywords):
            return prompt
    return ""


def _is_english_prompt(text: str) -> bool:
    """30文字超で日本語を含まない場合、ユーザー記述の英語プロンプトと判断する。
    キーワードマッチングによる上書きを防ぐためのガード。"""
    if len(text) < 30:
        return False
    return not any('぀' <= c <= '鿿' for c in text)


def _scene_count(duration: int) -> int:
    if duration <= 15:
        return int(os.getenv("DEFAULT_SCENES_15", "3"))
    if duration <= 30:
        return int(os.getenv("DEFAULT_SCENES_30", "5"))
    return int(os.getenv("DEFAULT_SCENES_60", "8"))


def _distribute_duration(total: int, count: int) -> List[int]:
    base = total // count
    rem = total % count
    return [base + (1 if i < rem else 0) for i in range(count)]


def _timing_text(parsed: Dict) -> str:
    dialogue_text = "\n".join(turn.get("text", "") for turn in parsed.get("dialogue", []) if turn.get("text"))
    speech_text = dialogue_text or parsed.get("narration", "")
    return "\n".join([
        speech_text,
        parsed.get("subtitle", ""),
        parsed.get("overlay_text", ""),
    ]).strip()


def _estimate_scene_duration(parsed: Dict, output_format: str, unbounded: bool = False) -> float:
    if parsed.get("type") == "flash":
        return PHF_FLASH_DURATION
    text = re.sub(r"\s+", "", _timing_text(parsed))
    if not text:
        return 3.0
    chars_per_second = float(os.getenv("SCENE_TIMING_CHARS_PER_SECOND", "8.5"))
    padding = float(os.getenv("SCENE_TIMING_PADDING_SECONDS", "0.25"))
    duration = len(text) / chars_per_second + padding
    if "[graphic:title]" in parsed.get("visual", "").lower():
        duration = max(duration, 5.0)
    min_duration = 2.4 if output_format == "standard_landscape" else 3.0
    if unbounded and output_format == "standard_landscape":
        return round(max(min_duration, duration), 1)
    max_duration = 16.0 if output_format == "standard_landscape" else 10.0
    return round(max(min_duration, min(max_duration, duration)), 1)


def _is_silent_end_card(parsed: Dict) -> bool:
    if (parsed.get("narration") or "").strip() or (parsed.get("subtitle") or "").strip():
        return False
    visual = (parsed.get("visual") or "").lower()
    if any((turn.get("text") or "").strip() for turn in parsed.get("dialogue") or []):
        return False
    return "[graphic" in visual or bool(parsed.get("overlay_text"))


def _cap_short_silent_end_card(durations: List[float], parsed_items: List[Dict], output_format: str) -> List[float]:
    if output_format != "short_vertical" or not durations or not parsed_items:
        return durations
    last = parsed_items[-1]
    if not _is_silent_end_card(last):
        return durations
    capped = list(durations)
    original_total = sum(float(x) for x in capped)
    capped[-1] = round(min(float(capped[-1]), SHORT_SILENT_END_CARD_SECONDS), 3)
    spare = round(original_total - sum(float(x) for x in capped), 3)
    if spare > 0.05 and len(capped) > 1:
        body_indices = list(range(len(capped) - 1))
        add_each = spare / len(body_indices)
        for idx in body_indices:
            capped[idx] = round(float(capped[idx]) + add_each, 3)
        drift = round(original_total - sum(float(x) for x in capped), 3)
        if abs(drift) > 0.001:
            capped[body_indices[-1]] = round(float(capped[body_indices[-1]]) + drift, 3)
    return capped


def _apply_talker_visual(visual: str, speaker: str | None) -> str:
    if not speaker:
        return visual
    if "[graphic:bar_chart]" in visual.lower() or "[graphic:flow]" in visual.lower():
        return visual
    talker_tag = f"[graphic:talker_{speaker}]"
    if "[graphic" in visual.lower():
        return re.sub(r"\[graphic(?::[^\]]+)?\]", talker_tag, visual, count=1, flags=re.IGNORECASE)
    return visual


def _is_simultaneous_visual(visual: str) -> bool:
    lowered = (visual or "").lower()
    return "[graphic:talkers_" in lowered or "[simultaneous]" in lowered


def _should_show_single_talker(visual: str, speaker: str | None) -> bool:
    lowered = (visual or "").lower()
    normalized_speaker = normalize_speaker(speaker)
    if "[graphic:meeting_room]" in lowered or "[graphic" not in lowered:
        return True
    if normalized_speaker in {"AnalystK", "Major"} and (
        "[graphic:light_text]" in lowered
        or "[graphic:dark_text]" in lowered
        or re.search(r"\[graphic\]\s*$", visual or "", re.IGNORECASE)
    ):
        return True
    return False


def _expand_dialogue_turns(parsed: Dict) -> List[Dict]:
    if parsed.get("type") == "flash":
        return [parsed]
    dialogue = [turn for turn in parsed.get("dialogue", []) if turn.get("text")]
    if len(dialogue) == 1:
        item = dict(parsed)
        visual = item.get("visual", "")
        if _should_show_single_talker(visual, dialogue[0].get("speaker")):
            item["visual"] = _apply_talker_visual(visual, dialogue[0].get("speaker"))
        return [item]
    if not dialogue:
        return [parsed]
    if _is_simultaneous_visual(parsed.get("visual", "")):
        item = dict(parsed)
        item["simultaneous_dialogue"] = True
        item["narration"] = "\n".join(turn.get("text", "") for turn in dialogue)
        return [item]

    expanded = []
    for idx, turn in enumerate(dialogue):
        speaker = turn.get("speaker")
        item = dict(parsed)
        item["narration"] = turn.get("text", "")
        item["subtitle"] = parsed.get("subtitle", "")
        item["dialogue"] = [turn]
        item["visual"] = _apply_talker_visual(parsed.get("visual", ""), speaker)
        keep_insert = parsed.get("insert_layer") in {"warning", "alert", "danger", "news"}
        if idx > 0 and not keep_insert:
            item.pop("insert_video_id", None)
            item.pop("insert_position", None)
            item["overlay_text"] = ""
        expanded.append(item)
    return expanded


def _looks_like_common_instruction(block: str) -> bool:
    b = (block or "").strip()
    if not b:
        return True
    first = b.splitlines()[0].strip()
    if MARKDOWN_RULE_RE.match(b):
        return True
    if first.startswith("#") and not _has_script_content(b):
        return True
    if first.startswith("##") and not first.startswith("###") and not _has_script_content(b):
        return True
    if first.startswith(("共通指示", "全体指示", "全体設定", "制作指示", "Common instructions", "Common Instruction")):
        return True
    labels = ("映像:", "映像：", "ナレーション:", "ナレーション：", "字幕:", "字幕：", "visual:", "Visual:", "narration:", "Narration:", "subtitle:", "Subtitle:")
    if not any(x in b for x in labels) and any(x in b for x in ("No text", "No letters", "9:16", "1080", "ドキュメンタリー調")):
        return True
    return False


def _split_script_blocks(script: str) -> List[str]:
    script = (script or "").strip()
    if not script:
        return []
    if "\n\n" in script:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", script) if b.strip()]
    else:
        lines = [b.strip() for b in script.splitlines() if b.strip()]
        visual_labels = ("映像:", "映像：", "visual:", "Visual:")
        if any(line.startswith(visual_labels) for line in lines):
            blocks = []
            current = []
            for line in lines:
                if (
                    line.startswith(visual_labels)
                    and current
                    and not all(_is_bgm_directive_only(item) for item in current)
                ):
                    blocks.append("\n".join(current).strip())
                    current = []
                current.append(line)
            if current:
                blocks.append("\n".join(current).strip())
        else:
            blocks = lines
    expanded = []
    current = []
    for block in blocks:
        if current:
            expanded.append("\n".join(current).strip())
            current = []
        for line in block.splitlines():
            if FLASH_TAG_RE.search(line):
                if current:
                    expanded.append("\n".join(current).strip())
                current = [line.strip()]
                continue
            current_is_flash = bool(current and FLASH_TAG_RE.search(current[0]))
            starts_new_scene = (
                line.startswith(("映像:", "映像：", "visual:", "Visual:"))
                or ("[graphic" in line.lower())
                or (CHARACTER_LINE_RE.match(line) and normalize_speaker(CHARACTER_LINE_RE.match(line).group(1)) in {normalize_speaker(s) for s in KNOWN_SPEAKERS})
            )
            if current_is_flash and starts_new_scene:
                expanded.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            expanded.append("\n".join(current).strip())
            current = []
    if current:
        expanded.append("\n".join(current).strip())
    return [b for b in expanded if not _looks_like_common_instruction(b)]


def _parse_script_block(block: str, fallback_visual: str) -> Dict:
    flash_match = FLASH_TAG_RE.search(block or "")
    if flash_match:
        raw_word = flash_match.group(1).strip()
        raw_prompt = (flash_match.group(2) or "").strip()
        preset_word, preset_prompt = FLASH_PRESETS.get(raw_word.lower(), (raw_word, raw_word))
        word = preset_word
        prompt = raw_prompt or preset_prompt
        narration_lines = []
        subtitle_lines = []
        for raw in block.splitlines():
            line = FLASH_TAG_RE.sub("", raw).strip().strip("*").strip()
            if not line:
                continue
            if line.startswith(("映像:", "映像：", "visual:", "Visual:")):
                continue
            if line.startswith(("ナレーション:", "ナレーション：", "narration:", "Narration:")):
                text = line.split(":", 1)[-1] if ":" in line else line.split("：", 1)[-1]
                cleaned = _clean_spoken_text(text)
                narration_lines.append(cleaned)
                if cleaned:
                    dialogue.append({"speaker": "Narrator", "text": cleaned})
                continue
            if line.startswith(("字幕:", "字幕：", "subtitle:", "Subtitle:")):
                text = line.split(":", 1)[-1] if ":" in line else line.split("：", 1)[-1]
                subtitle_lines.append(_clean_spoken_text(text))
                continue
            narration_lines.append(_clean_spoken_text(line))
        narration = "\n".join([x.strip() for x in narration_lines if x.strip()]).strip()
        subtitle = "\n".join([x.strip() for x in subtitle_lines if x.strip()]).strip()
        return {
            "type": "flash",
            "visual": prompt,
            "narration": narration,
            "subtitle": subtitle,
            "overlay_text": "",
            "dialogue": [],
            "flash_word": word,
            "flash_prompt": prompt,
        }

    visual = ""
    insert_video_id = None
    insert_options = {}
    scene_options = {}
    bgm_filename = None
    narration_lines = []
    dialogue = []
    subtitle_lines = []
    overlay_lines = []
    mode = None
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if MARKDOWN_RULE_RE.match(line):
            continue
        if line.startswith("#"):
            if "[graphic" not in line.lower() and "[insert" not in line.lower() and "[bgm" not in line.lower() and not _has_script_content(line):
                continue
            line = re.sub(r"^#+\s*", "", line).strip()
        line, insert_video_id, insert_options = _strip_insert_tag(line, insert_video_id, insert_options)
        line, bgm_filename = _strip_bgm_tag(line, bgm_filename)
        line, scene_options = _strip_motoko_overlay_tags(line, scene_options)
        if not line:
            continue
        if "[graphic" in line.lower() and not line.startswith(("譏蜒・", "譏蜒擾ｼ・", "visual:", "Visual:")):
            graphic_visual = line[line.lower().find("[graphic"):].strip()
            if scene_options.get("graphic_overlay_wildcard") or scene_options.get("motoko_lipsync"):
                scene_options["graphic_overlay_prompt"] = _sanitize_graphic_overlay_prompt(graphic_visual)
                if not visual.strip():
                    visual = "[graphic:talker_AnalystK] AnalystK"
                mode = None
                continue
            else:
                visual = graphic_visual
            mode = "visual"
            continue
        if line.startswith(("映像:", "映像：", "visual:", "Visual:")):
            if line.startswith("映像："):
                visual = line[3:]
            elif line.startswith("映像:"):
                visual = line[3:]
            elif line.startswith("Visual:"):
                visual = line[7:]
            elif line.startswith("visual:"):
                visual = line[7:]
            else:
                visual = line.split(":", 1)[-1]
            if "[graphic" in visual.lower() and (scene_options.get("graphic_overlay_wildcard") or scene_options.get("motoko_lipsync")):
                scene_options["graphic_overlay_prompt"] = _sanitize_graphic_overlay_prompt(visual[visual.lower().find("[graphic"):].strip())
                visual = "[graphic:talker_AnalystK] AnalystK"
            mode = "visual"
            continue
        if line.startswith(("テキスト:", "テキスト：", "overlay:", "text_overlay:")):
            txt = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1]
            overlay_lines.append(txt.strip())
            mode = "overlay"
            continue
        if line.startswith(("ナレーション:", "ナレーション：", "narration:", "Narration:")):
            text = line.split(":", 1)[-1] if ":" in line else line.split("：", 1)[-1]
            cleaned = _clean_spoken_text(text)
            narration_lines.append(cleaned)
            if cleaned:
                dialogue.append({"speaker": "Narrator", "text": cleaned})
            mode = "narration"
            continue
        speaker_match = SPEAKER_LINE_RE.match(line)
        if speaker_match:
            speaker = normalize_speaker(speaker_match.group(1))
            text = _clean_spoken_text(speaker_match.group(2))
            dialogue.append({"speaker": speaker, "text": text})
            narration_lines.append(text)
            mode = "narration"
            continue
        character_match = CHARACTER_LINE_RE.match(line)
        if character_match and normalize_speaker(character_match.group(1)) in {normalize_speaker(s) for s in KNOWN_SPEAKERS}:
            speaker = normalize_speaker(character_match.group(1))
            text = _clean_spoken_text(character_match.group(2))
            dialogue.append({"speaker": speaker, "text": text})
            narration_lines.append(text)
            mode = "narration"
            continue
        if line.startswith(("字幕:", "字幕：", "subtitle:", "Subtitle:")):
            subtitle_lines.append(line.split(":", 1)[-1] if ":" in line else line.split("：", 1)[-1])
            mode = "subtitle"
            continue
        if mode == "visual":
            if "[graphic" in visual.lower():
                visual += "\n" + line
            else:
                visual += " " + line
        elif mode == "overlay":
            overlay_lines.append(_clean_spoken_text(line))
        elif mode == "subtitle":
            subtitle_lines.append(_clean_spoken_text(line))
        else:
            narration_lines.append(_clean_spoken_text(line))

    narration = "\n".join([x.strip() for x in narration_lines if x.strip()]).strip()
    subtitle = "\n".join([x.strip() for x in subtitle_lines if x.strip()]).strip()
    overlay_text = "\n".join([x.strip() for x in overlay_lines if x.strip()]).strip()

    used_fallback_visual = not bool(visual.strip())
    visual_text = visual.strip() or fallback_visual
    if "[graphic" in visual_text.lower():
        pass
    elif _is_english_prompt(visual_text):
        pass  # ユーザーが書いた英語プロンプトはそのまま使用
    else:
        matched = _match_visual_prompt(visual_text)
        if matched:
            visual_text = matched

    parsed = {
        "visual": visual_text,
        "narration": narration or subtitle,
        "subtitle": subtitle,
        "overlay_text": overlay_text,
        "dialogue": dialogue,
        "_used_fallback_visual": used_fallback_visual,
    }
    if insert_video_id:
        parsed["insert_video_id"] = insert_video_id
        parsed["insert_position"] = "bottom_right"
        if insert_options.get("insert_layer"):
            parsed["insert_layer"] = insert_options["insert_layer"]
    if bgm_filename:
        parsed["bgm_filename"] = bgm_filename
    if scene_options.get("motoko_lipsync"):
        parsed["motoko_lipsync"] = True
    if scene_options.get("lipsync_display_mode"):
        parsed["lipsync_display_mode"] = scene_options["lipsync_display_mode"]
    if scene_options.get("lipsync_source_set"):
        parsed["lipsync_source_set"] = scene_options["lipsync_source_set"]
    if scene_options.get("lipsync_source_mode"):
        parsed["lipsync_source_mode"] = scene_options["lipsync_source_mode"]
    if scene_options.get("graphic_overlay_prompt"):
        parsed["graphic_overlay_prompt"] = _sanitize_graphic_overlay_prompt(scene_options["graphic_overlay_prompt"])
    return parsed


def _build_custom_script_scenes(project: Dict, prefix: str):
    blocks = _split_script_blocks(project.get("script", ""))
    if not blocks:
        return None
    duration = int(project.get("duration", 60))
    output_format = project.get("format", "short_vertical")
    fixed_short_body_duration = _fixed_short_body_duration(project)
    if fixed_short_body_duration is not None:
        duration = fixed_short_body_duration
    script_timed_short = output_format == "short_vertical" and project.get("short_timing_mode", "fixed_57") == "script"
    standard_script_unbounded = _is_standard_script_unbounded(project)
    max_blocks = len(blocks) if output_format == "standard_landscape" else (60 if script_timed_short else 12)
    count = max(1, min(len(blocks), max_blocks))
    blocks = blocks[:count]
    prompt = project.get("prompt", "")
    parsed_items = []
    last_visual = ""
    active_lipsync_source_set = str(project.get("analystk_lipsync_source_set") or "anime")
    for idx, block in enumerate(blocks):
        fallback_visual = DEFAULT_VISUALS[round(idx * (len(DEFAULT_VISUALS) - 1) / max(1, count - 1))]
        parsed = _parse_script_block(block, fallback_visual)
        if parsed.get("lipsync_source_set"):
            active_lipsync_source_set = parsed["lipsync_source_set"]
        elif parsed.get("motoko_lipsync"):
            parsed["lipsync_source_set"] = active_lipsync_source_set
        if parsed.get("_used_fallback_visual") and last_visual and parsed.get("type") != "flash":
            parsed["visual"] = last_visual
        if prompt and parsed["visual"] == fallback_visual:
            parsed["visual"] = f"{fallback_visual}, topic: {prompt}"
        if parsed.get("type") != "flash" and parsed.get("visual"):
            last_visual = parsed["visual"]
        parsed_items.extend(_expand_dialogue_turns(parsed))

    if output_format == "standard_landscape" or (
        output_format == "short_vertical" and project.get("short_timing_mode", "fixed_57") == "script"
    ):
        durations = [_estimate_scene_duration(parsed, output_format, standard_script_unbounded) for parsed in parsed_items]
    else:
        durations = _distribute_duration(duration, len(parsed_items))
        durations = _cap_short_silent_end_card(durations, parsed_items, output_format)

    scenes = []
    t = 0
    for idx, parsed in enumerate(parsed_items):
        visual = parsed["visual"]
        d = durations[idx]
        # graphicタグがある場合はprefixを付けない
        if "[graphic" in visual.lower():
            visual_prompt = visual
        else:
            visual_prompt = f"{prefix} {visual}, no readable text."
        scenes.append({
            "scene_id": idx + 1,
            "start": t,
            "end": t + d,
            "duration": d,
            "visual_prompt": visual_prompt,
            "negative_prompt": NEGATIVE,
            "narration": parsed["narration"],
            "subtitle": parsed["subtitle"],
            "overlay_text": parsed.get("overlay_text", ""),
            "speaker": parsed.get("dialogue", [{}])[0].get("speaker") if parsed.get("dialogue") else None,
            "dialogue": parsed.get("dialogue", []),
            "simultaneous_dialogue": parsed.get("simultaneous_dialogue", False),
            "insert_video_id": parsed.get("insert_video_id"),
            "insert_position": parsed.get("insert_position"),
            "insert_layer": parsed.get("insert_layer"),
            "bgm_filename": parsed.get("bgm_filename"),
            "motoko_lipsync": parsed.get("motoko_lipsync", False),
            "lipsync_display_mode": parsed.get("lipsync_display_mode"),
            "lipsync_source_set": parsed.get("lipsync_source_set"),
            "lipsync_source_mode": parsed.get("lipsync_source_mode"),
            "graphic_overlay_prompt": parsed.get("graphic_overlay_prompt"),
            "is_flash": parsed.get("type") == "flash",
            "flash_word": parsed.get("flash_word"),
            "flash_prompt": parsed.get("flash_prompt"),
        })
        t += d
    return scenes


def build_scenes(project: Dict) -> List[Dict]:
    duration = int(project.get("duration", 60))
    fixed_short_body_duration = _fixed_short_body_duration(project)
    if fixed_short_body_duration is not None:
        duration = fixed_short_body_duration
    style = project.get("style", "serious_documentary")
    prefix = STYLE_PREFIXES.get(style, STYLE_PREFIXES["serious_documentary"])

    custom = _build_custom_script_scenes(project, prefix)
    if custom:
        return custom

    count = _scene_count(duration)
    durations = _distribute_duration(duration, count)
    title = project.get("title", "")
    prompt = project.get("prompt", "")

    visual_prompts = DEFAULT_VISUALS
    narrations = [
        f"{title}。これは、いま多くの現場で起きている問題です。",
        "見えているものだけでは、本当の負担はわかりません。",
        "数字は静かですが、現場には重くのしかかります。",
        "大切なのは、表面的な売上ではなく、手元に残るお金です。",
        "小さな負担の積み重ねが、事業の判断を変えていきます。",
        "だからこそ、現場の目線で見直す必要があります。",
        "この問題は、他人事ではありません。",
        "事実を知ることから、変化は始まります。",
    ]
    subtitles = ["" for _ in narrations]

    scenes = []
    t = 0
    for idx in range(count):
        source_idx = round(idx * (len(visual_prompts) - 1) / max(1, count - 1))
        d = durations[idx]
        scenes.append({
            "scene_id": idx + 1,
            "start": t,
            "end": t + d,
            "duration": d,
            "visual_prompt": f"{prefix} {visual_prompts[source_idx]}, no readable text.",
            "negative_prompt": NEGATIVE,
            "narration": narrations[source_idx],
            "subtitle": subtitles[source_idx],
        })
        t += d
    return scenes
