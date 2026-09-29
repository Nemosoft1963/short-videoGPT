import os
import re
from typing import Dict, List

NEGATIVE = "No text, no letters, no subtitles, no logos, no watermark, no anime, no cartoon, no 3D render, no neon colors, no colorful effects, no smiling business people, no western shop, no modern luxury office."

STYLE_PREFIXES = {
    "serious_documentary": "Realistic Japanese documentary footage, serious, quiet, intellectual, heavy atmosphere, muted colors, washi beige, sumi black, vermilion accents, restrained camera movement.",
    "small_business_awareness": "Realistic Japanese small business documentary footage, quiet and dignified, serious tone, traditional interior, muted colors.",
    "tax_issue": "Serious Japanese documentary footage about small business tax pressure, accounting papers, ledgers, quiet heavy atmosphere, realistic.",
    "recruiting": "Realistic Japanese logistics and workplace documentary footage, calm, professional, trustworthy, muted colors.",
    "product_intro": "Clean realistic product explanation video, calm, simple, professional, minimal graphics, muted colors.",
}

DEFAULT_VISUALS = [
    "symbolic opening shot for the topic, realistic Japanese documentary style",
    "main subject shown through realistic close-up objects and quiet human presence",
    "documents and hands showing the practical problem in daily operations",
    "serious office or shop scene showing pressure and decision-making",
    "quiet street or workplace scene suggesting broader social context",
    "close-up of key object, document, or tool, restrained documentary style",
    "minimal ending background, realistic paper texture, quiet and serious",
    "final abstract calm background, no text",
]


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


def _looks_like_common_instruction(block: str) -> bool:
    """台本ZIPの先頭にある共通指示を、動画シーンとして読まないための判定です。"""
    b = (block or "").strip()
    if not b:
        return True
    first = b.splitlines()[0].strip()
    if first.startswith(("共通指示", "全体指示", "全体設定", "制作指示", "Common instructions", "Common Instruction")):
        return True
    # 映像・ナレーション・字幕のいずれも含まず、禁止事項だけのブロックはシーンにしない
    labels = ("映像:", "映像：", "ナレーション:", "ナレーション：", "字幕:", "字幕：", "visual:", "Visual:", "narration:", "Narration:", "subtitle:", "Subtitle:")
    if not any(x in b for x in labels) and any(x in b for x in ("No text", "No letters", "9:16", "1080", "ドキュメンタリー調")):
        return True
    return False


def _split_script_blocks(script: str) -> List[str]:
    script = (script or "").strip()
    if not script:
        return []
    # 空行区切りを優先。空行がなければ、1行1シーン。
    if "\n\n" in script:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", script) if b.strip()]
    else:
        blocks = [b.strip() for b in script.splitlines() if b.strip()]
    return [b for b in blocks if not _looks_like_common_instruction(b)]


def _parse_script_block(block: str, fallback_visual: str) -> Dict:
    visual = ""
    narration_lines = []
    subtitle_lines = []
    mode = None
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("映像:", "映像：", "visual:", "Visual:")):
            visual = line.split(":", 1)[-1] if ":" in line else line.split("：", 1)[-1]
            mode = "visual"
            continue
        if line.startswith(("ナレーション:", "ナレーション：", "narration:", "Narration:")):
            narration_lines.append(line.split(":", 1)[-1] if ":" in line else line.split("：", 1)[-1])
            mode = "narration"
            continue
        if line.startswith(("字幕:", "字幕：", "subtitle:", "Subtitle:")):
            subtitle_lines.append(line.split(":", 1)[-1] if ":" in line else line.split("：", 1)[-1])
            mode = "subtitle"
            continue
        if mode == "visual":
            visual += " " + line
        elif mode == "subtitle":
            subtitle_lines.append(line)
        else:
            narration_lines.append(line)

    narration = "\n".join([x.strip() for x in narration_lines if x.strip()]).strip()
    subtitle = "\n".join([x.strip() for x in subtitle_lines if x.strip()]).strip() or narration
    return {
        "visual": visual.strip() or fallback_visual,
        "narration": narration or subtitle,
        "subtitle": subtitle,
    }


def _build_custom_script_scenes(project: Dict, prefix: str):
    blocks = _split_script_blocks(project.get("script", ""))
    if not blocks:
        return None
    duration = int(project.get("duration", 60))
    count = max(1, min(len(blocks), 12))
    blocks = blocks[:count]
    durations = _distribute_duration(duration, count)
    prompt = project.get("prompt", "")
    scenes = []
    t = 0
    for idx, block in enumerate(blocks):
        fallback_visual = DEFAULT_VISUALS[round(idx * (len(DEFAULT_VISUALS) - 1) / max(1, count - 1))]
        parsed = _parse_script_block(block, fallback_visual)
        visual = parsed["visual"]
        if prompt and visual == fallback_visual:
            visual = f"{fallback_visual}, topic: {prompt}"
        d = durations[idx]
        scenes.append({
            "scene_id": idx + 1,
            "start": t,
            "end": t + d,
            "duration": d,
            "visual_prompt": f"{prefix} {visual}, no readable text.",
            "negative_prompt": NEGATIVE,
            "narration": parsed["narration"],
            "subtitle": parsed["subtitle"],
        })
        t += d
    return scenes


def build_scenes(project: Dict) -> List[Dict]:
    duration = int(project.get("duration", 60))
    style = project.get("style", "serious_documentary")
    prefix = STYLE_PREFIXES.get(style, STYLE_PREFIXES["serious_documentary"])

    custom = _build_custom_script_scenes(project, prefix)
    if custom:
        return custom

    count = _scene_count(duration)
    durations = _distribute_duration(duration, count)
    title = project.get("title", "土地があっても、銀行は貸さない")
    prompt = project.get("prompt", "")

    if "消費税" in prompt or "銀行" in title or "土地" in title:
        visual_prompts = [
            "an old traditional Japanese wagashi shop in the morning, wooden storefront, old signboard without readable text, soft natural light",
            "close-up of an old wooden desk in a Japanese small business office, accounting ledger, calculator, land registry documents, tax papers, aged paper texture",
            "a quiet Japanese bank consultation counter, serious bank officer looking at financial documents, loan application papers on the desk",
            "invoices, supplier bills, payroll papers, rent invoice, tax payment slips piling up on a small business desk, hands of an older Japanese shop owner",
            "older Japanese small business owner sitting quietly in a traditional shop office, looking down at accounting books, tired but dignified",
            "quiet traditional Japanese shopping street in the evening, half-closed shutters, few pedestrians, realistic documentary footage",
            "close-up of a ledger on a wooden desk, a Japanese shop owner's hand slowly closing a financial document, old paper, calculator",
            "minimal realistic texture of Japanese washi paper and dark sumi black shadow, quiet serious documentary ending background",
        ]
        narrations = [
            "土地二千五百万円。それでも、銀行は貸しません。なぜでしょうか。",
            "創業五十二年の和菓子店。土地はある。お客様もいる。それでも、資金繰りは苦しい。",
            "銀行が見るのは、土地の価値だけではありません。毎月の資金繰り。返済できる力。そして、税金を払った後に残るお金です。",
            "消費税は、売上があれば発生します。赤字でも、資金がなくても、納付は求められます。これが中小企業の現実です。",
            "土地があるから大丈夫。老舗だから大丈夫。そうはなりません。消費税が、事業の体力を削っていくからです。",
            "店を守る力は、売上だけでは決まりません。手元に残るお金がなければ、事業は続けられません。",
            "消費税は、単なる預り金ではありません。中小企業の資金繰りを直撃する、重い負担です。",
            "この現実を、広げなければならない。",
        ]
        subtitles = [
            "土地2,500万円。\nそれでも、銀行は貸しません。\nなぜでしょうか？",
            "創業52年の和菓子店。\n土地はある。お客様もいる。\nそれでも、資金繰りは苦しい。",
            "銀行が見るのは、土地の価値だけではありません。\n税金を払った後に残るお金です。",
            "消費税は、売上があれば発生します。\n赤字でも、資金がなくても、納付は求められます。",
            "土地があるから大丈夫。\n老舗だから大丈夫。\nそうはなりません。",
            "手元に残るお金がなければ、\n事業は続けられません。",
            "消費税は、単なる預り金ではありません。\n中小企業の資金繰りを直撃する、重い負担です。",
            "この現実を、広げなければならない。",
        ]
    else:
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
        subtitles = [n for n in narrations]

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
