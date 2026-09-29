import os
import re
from typing import Dict, List

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


def _match_visual_prompt(text: str) -> str:
    """テキストからキーワードマッチングで映像プロンプトを返す"""
    for keywords, prompt in VISUAL_KEYWORD_MAP:
        if any(kw in text for kw in keywords):
            return prompt
    return ""


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
    b = (block or "").strip()
    if not b:
        return True
    first = b.splitlines()[0].strip()
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

    # 映像プロンプトが日本語の場合、キーワードマッチングで英語に変換
    visual_text = visual.strip() or fallback_visual
    matched = _match_visual_prompt(visual_text)
    if matched:
        visual_text = matched

    return {
        "visual": visual_text,
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
