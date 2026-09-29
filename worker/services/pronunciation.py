import json
import os
import re
from pathlib import Path


STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
PRONUNCIATION_MAP_JSON = os.getenv(
    "TTS_PRONUNCIATION_MAP",
    os.getenv("QWEN3_TTS_PRONUNCIATION_MAP", ""),
)
PRONUNCIATION_MAP_PATH = (
    os.getenv("TTS_PRONUNCIATION_MAP_PATH")
    or os.getenv("QWEN3_TTS_PRONUNCIATION_MAP_PATH")
    or str(STORAGE_DIR / "config" / "pronunciation_map.json")
)
READING_DIRECTIVE_RE = re.compile(r"\[(?:読み|よみ|read)\s*[:：]\s*([^=＝:：\]]+?)\s*[=＝:：]\s*([^\]]+?)\]", re.IGNORECASE)
INLINE_READING_RE = re.compile(r"([^\s、。！？「」『』（）()\[\]［］《》]+)《(?:読み|よみ|read)\s*[:：]\s*([^》]+?)》", re.IGNORECASE)


DEFAULT_PRONUNCIATION_MAP = {
    "Qwen3-TTS": "キューウェンスリー ティーティーエス",
    "Qwen3": "キューウェンスリー",
    "StyleBertVITS2": "スタイルバートビッツ ツー",
    "Style-Bert-VITS2": "スタイルバートビッツ ツー",
    "GPT": "ジーピーティ",
    "GMN": "ジーエムエヌ",
    "META": "めた",
    "GROCK": "ぐろっく",
    "Grock": "ぐろっく",
    "Claude": "クロード",
    "CLAUDE": "クロード",
    "AI": "エーアイ",
    "OS": "オーエス",
    "DX": "ディーエックス",
    "SRI": "エスアールアイ",
    "S1": "エスワン",
    "S2": "エスツー",
    "S3": "エススリー",
    "S4": "エスフォー",
    "S5": "エスファイブ",
    "S6": "エスシックス",
    "S7": "エスセブン",
    "S8": "エスエイト",
    "B2B": "ビートゥービー",
    "VAT": "ブイエーティー",
    "EU": "イーユー",
    "USA": "ユーエスエー",
    "FICA": "ファイカ",
    "Social Security": "ソーシャル セキュリティ",
    "Medicare": "メディケア",
    "人頭税": "じんとうぜい",
    "消費税の闇": "しょうひぜいのやみ",
    "預り金": "あずかりきん",
    "片翼": "かたよく",
    "消費税率": "しょうひぜいりつ",
    "消費税": "しょうひぜい",
    "雇用保護": "こようほご",
    "輸出還付": "ゆしゅつかんぷ",
    "借入": "かりいれ",
    "人件費": "じんけんひ",
    "外注費": "がいちゅうひ",
    "外注": "がいちゅう",
    "外食": "がいしょく",
    "外される": "はずされる",
    "外した": "はずした",
    "三つ": "みっつ",
    "控除": "こうじょ",
    "重複督促": "ちょうふくとくそく",
    "俯瞰": "ふかん",
    "上書き": "うわがき",
    "社保": "しゃほ",
    "蝕む": "むしばむ",
    "5つの": "いつつの",
    "近道君": "ちかみちくん",
    "具体的な": "ぐたいてき",
    "インボイス": "インボイス",
    "第二法人事業税": "だいにほうじんじぎょうぜい",
    "法人事業税": "ほうじんじぎょうぜい",
    "法人企業統計": "ほうじんきぎょうとうけい",
    "法人税": "ほうじんぜい",
    "利益剰余金": "りえきじょうよきん",
    "内部留保": "ないぶりゅうほ",
    "信用創造": "しんようそうぞう",
    "経済成長": "けいざいせいちょう",
    "社会保険料": "しゃかいほけんりょう",
    "設計図": "せっけいず",
    "医療崩壊": "いりょうほうかい",
    "訪問介護": "ほうもんかいご",
    "輝いている": "かがやいている",
    "瀬戸際": "せとぎわ",
    "付加価値": "ふかかち",
    "四文字": "よんもじ",
    "口座": "こうざ",
    "現場": "げんば",
    "物語": "ものがたり",
    "寓話": "ぐうわ",
    "善意": "ぜんい",
    "外された": "はずされた",
    "誠実な": "せいじつな",
    "夢から": "ゆめから",
    "情報を": "じょうほうを",
    "設計": "せっけい",
    "爆発": "ばくはつ",
    "怒り": "イカリ",
    "信念": "しんねん",
    "言葉": "ことば",
    "真実": "しんじつ",
    "留まる": "とどまる",
    "止めていた": "とめていた",
    "後ろに": "うしろに",
    "将来": "しょうらい",
    "近道": "ちかみち",
    "外": "そと",
    "鏡の国": "かがみのくに",
    "鏡": "かがみ",
    "課税仕入": "かぜいしいれ",
    "仕入税額控除": "しいれぜいがくこうじょ",
    "差押え": "さしおさえ",
    "差し押さえ": "さしおさえ",
    "休廃業": "きゅうはいぎょう",
    "現場主権": "げんばしゅけん",
    "国家": "こっか",
    "国民": "こくみん",
    "国": "くに",
    "海外": "かいがい",
    "国内": "こくない",
    "楯": "たて",
    "灯り": "あかり",
    "点呼": "てんこ",
}


def extract_pronunciation_overrides(text: str) -> tuple[str, dict[str, str]]:
    overrides: dict[str, str] = {}

    def directive_repl(match: re.Match[str]) -> str:
        source = match.group(1).strip()
        reading = match.group(2).strip()
        if source and reading:
            overrides[source] = reading
        return ""

    def inline_repl(match: re.Match[str]) -> str:
        source = match.group(1).strip()
        reading = match.group(2).strip()
        if source and reading:
            overrides[source] = reading
        return source

    cleaned = READING_DIRECTIVE_RE.sub(directive_repl, text or "")
    cleaned = INLINE_READING_RE.sub(inline_repl, cleaned)
    return cleaned, overrides


def load_pronunciation_map() -> dict[str, str]:
    mapping = dict(DEFAULT_PRONUNCIATION_MAP)
    if PRONUNCIATION_MAP_PATH:
        try:
            source = Path(PRONUNCIATION_MAP_PATH)
            if source.exists():
                loaded = json.loads(source.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    mapping.update({str(k): str(v) for k, v in loaded.items()})
        except Exception:
            pass
    if PRONUNCIATION_MAP_JSON:
        try:
            loaded = json.loads(PRONUNCIATION_MAP_JSON)
            if isinstance(loaded, dict):
                mapping.update({str(k): str(v) for k, v in loaded.items()})
        except json.JSONDecodeError:
            pass
    return mapping


def replace_pronunciation_terms(text: str, extra_map: dict[str, str] | None = None) -> str:
    result = text
    mapping = load_pronunciation_map()
    if extra_map:
        mapping.update(extra_map)
    for source, reading in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if source:
            result = result.replace(source, reading)
    return result


def normalize_symbols(text: str) -> str:
    result = text
    result = result.replace("……", "。").replace("…", "、")
    result = result.replace("――", "、").replace("—", "、")
    result = result.replace("・", "、")
    return re.sub(r"\s+", " ", result).strip()


def number_to_kana(number: int) -> str:
    if number == 0:
        return "ぜろ"
    small = ["", "いち", "に", "さん", "よん", "ご", "ろく", "なな", "はち", "きゅう"]
    units = [(1000, "せん"), (100, "ひゃく"), (10, "じゅう")]

    def under_10000(value: int) -> str:
        parts: list[str] = []
        rest = value
        for unit, label in units:
            digit = rest // unit
            rest %= unit
            if digit == 0:
                continue
            if digit == 1:
                parts.append(label)
            else:
                parts.append(small[digit] + label)
        if rest:
            parts.append(small[rest])
        return "".join(parts)

    big_units = [(10**12, "ちょう"), (10**8, "おく"), (10**4, "まん")]
    parts: list[str] = []
    rest = number
    for unit, label in big_units:
        chunk = rest // unit
        rest %= unit
        if chunk:
            parts.append(under_10000(chunk) + label)
    if rest:
        parts.append(under_10000(rest))
    return "".join(parts)


def replace_numbers_with_kana(text: str) -> str:
    unit_map = {
        "%": "ぱーせんと",
        "％": "ぱーせんと",
        "円": "えん",
        "年": "ねん",
        "月": "がつ",
        "日": "にち",
        "人": "にん",
        "件": "けん",
        "回": "かい",
        "倍": "ばい",
        "万": "まん",
        "億": "おく",
        "兆": "ちょう",
    }

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        unit = match.group(2) or ""
        cleaned = raw.replace(",", "")
        if "." in cleaned:
            integer, fraction = cleaned.split(".", 1)
            kana = number_to_kana(int(integer or "0")) + "てん" + "".join(
                number_to_kana(int(ch)) for ch in fraction if ch.isdigit()
            )
        else:
            kana = number_to_kana(int(cleaned))
        return kana + "".join(unit_map.get(ch, ch) for ch in unit)

    return re.sub(r"(\d[\d,]*(?:\.\d+)?)([%％円年月日人件回倍万億兆]*)", repl, text)


def normalize_text_for_tts(text: str) -> str:
    cleaned, overrides = extract_pronunciation_overrides(text or "")
    normalized = replace_pronunciation_terms(cleaned, overrides)
    normalized = replace_numbers_with_kana(normalized)
    return normalize_symbols(normalized)
