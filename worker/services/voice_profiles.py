import json
import os
from functools import lru_cache
from typing import Any


DEFAULT_QWEN_MODEL = os.getenv("QWEN3_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
DEFAULT_QWEN_SPEAKER = os.getenv("QWEN3_TTS_SPEAKER", "chikamichi")


DEFAULT_VOICE_PROFILES: dict[str, dict[str, Any]] = {
    "GMN": {"tts_engine": "stylebertvits2", "model_id": 0, "speaker_id": 0, "style": "Neutral", "style_weight": 1.0},
    "YT": {"tts_engine": "stylebertvits2", "model_id": 1, "speaker_id": 0, "style": "Calm", "style_weight": 0.8},
    "META": {"tts_engine": "stylebertvits2", "model_id": 2, "speaker_id": 0, "style": "Happy", "style_weight": 1.5},
    "GPT": {"tts_engine": "stylebertvits2", "model_id": 3, "speaker_id": 0, "style": "Neutral", "style_weight": 1.2},
    "GROCK": {"tts_engine": "stylebertvits2", "model_id": 4, "speaker_id": 0, "style": "Neutral", "style_weight": 1.8, "sdp_ratio": 0.8},
    "CLAUDE": {"tts_engine": "stylebertvits2", "model_id": 3, "speaker_id": 0, "style": "Neutral", "style_weight": 1.2},
    "AnalystK": {
        "tts_engine": "qwen3tts",
        "qwen3_tts_model": DEFAULT_QWEN_MODEL,
        "qwen3_tts_mode": "voice_clone",
        "qwen3_tts_speaker": DEFAULT_QWEN_SPEAKER,
        "language": "Japanese",
        "qwen3_tts_instruct": "冷静で抑制された女性分析官の声。低めで芯があり、控えめに艶のある落ち着いた声質。標準日本語で一語ずつ明瞭に発音し、漢字・英字略語・専門語を正確に読む。感情は抑え、句読点で長く溜めず、短く歯切れよく話す。",
        "qwen3_tts_short_instruct": "冷静で抑制された女性分析官の声。低めで芯があり、ショート動画向けに少しテンポよく話す。落ち着きは維持しつつ、声に控えめな艶と柔らかさを少し強める。標準日本語で一語ずつ明瞭に発音し、漢字・英字略語・専門語を正確に読む。感情は抑え、句読点で長く溜めず、短く歯切れよく話す。",
        "speed_scale": 0.92,
        "short_speed_scale": 1.0,
        "model_id": 4,
        "speaker_id": 0,
        "style": "Neutral",
        "style_weight": 1.0,
        "sdp_ratio": 0.05,
        "noise": 0.25,
        "noisew": 0.35,
    },
    "Major": {
        "tts_engine": "stylebertvits2",
        "model_id": 6,
        "speaker_id": 0,
        "style": "Neutral",
        "style_weight": 1.0,
        "sdp_ratio": 0.25,
        "noise": 0.35,
        "noisew": 0.6,
        "speed_scale": 0.96,
    },
    "Narrator": {
        "tts_engine": "stylebertvits2",
        "model_id": 0,
        "speaker_id": 0,
        "style": "Neutral",
        "style_weight": 1.0,
        "sdp_ratio": 0.2,
        "noise": 0.35,
        "noisew": 0.55,
        "speed_scale": 0.94,
    },
    "Driver": {
        "tts_engine": "stylebertvits2",
        "speed_scale": 1.0,
        "model_id": 4,
        "speaker_id": 0,
        "style": "Happy",
        "style_weight": 1.15,
        "sdp_ratio": 0.2,
        "noise": 0.35,
        "noisew": 0.55,
    },
    "President": {
        "tts_engine": "stylebertvits2",
        "speed_scale": 0.92,
        "model_id": 4,
        "speaker_id": 0,
        "style": "Neutral",
        "style_weight": 1.25,
        "sdp_ratio": 0.28,
        "noise": 0.32,
        "noisew": 0.5,
    },
    "Banker": {
        "tts_engine": "stylebertvits2",
        "speed_scale": 0.98,
        "model_id": 3,
        "speaker_id": 0,
        "style": "Neutral",
        "style_weight": 1.05,
        "sdp_ratio": 0.18,
        "noise": 0.35,
        "noisew": 0.55,
    },
    "Father": {
        "tts_engine": "stylebertvits2",
        "speed_scale": 1.0,
        "model_id": 3,
        "speaker_id": 0,
        "style": "Happy",
        "style_weight": 1.2,
        "sdp_ratio": 0.2,
        "noise": 0.35,
        "noisew": 0.55,
    },
    "ChildBoy": {
        "tts_engine": "stylebertvits2",
        "speed_scale": 1.08,
        "model_id": 3,
        "speaker_id": 0,
        "style": "Surprise",
        "style_weight": 1.35,
        "sdp_ratio": 0.12,
        "noise": 0.38,
        "noisew": 0.58,
    },
    "InvestigatorS": {"tts_engine": "stylebertvits2", "model_id": 2, "speaker_id": 0, "style": "Happy", "style_weight": 1.0},
    "chikamichi": {
        "tts_engine": "qwen3tts",
        "speaker_id": 0,
        "qwen3_tts_model": DEFAULT_QWEN_MODEL,
        "qwen3_tts_mode": "voice_clone",
        "qwen3_tts_speaker": DEFAULT_QWEN_SPEAKER,
        "language": "Japanese",
    },
}


SPEAKER_ALIASES = {
    "Grock": "GROCK",
    "GROK": "GROCK",
    "Claude": "CLAUDE",
    "K": "AnalystK",
    "ANALYST_K": "AnalystK",
    "\u5206\u6790\u5b98K": "AnalystK",
    "\u5206\u6790\u5b98\uff2b": "AnalystK",
    "MAJOR": "Major",
    "\u5c11\u4f50": "Major",
    "Narration": "Narrator",
    "NARRATION": "Narrator",
    "\u30ca\u30ec\u30fc\u30b7\u30e7\u30f3": "Narrator",
    "\u30ca\u30ec\u30fc\u30bf\u30fc": "Narrator",
    "\u30c9\u30e9\u30a4\u30d0\u30fc": "Driver",
    "\u793e\u9577": "President",
    "\u9280\u884c\u62c5\u5f53\u8005": "Banker",
    "\u7236\u89aa": "Father",
    "\u5b50\u3069\u3082": "ChildBoy",
    "S": "InvestigatorS",
    "INVESTIGATOR_S": "InvestigatorS",
    "CHIKAMICHI": "chikamichi",
    "Chikamichi": "chikamichi",
    "\u8fd1\u9053": "chikamichi",
    "\u8fd1\u9053\u541b": "chikamichi",
    "\u30af\u30ed\u30fc\u30c9": "CLAUDE",
    "\u30af\u30ed\u30fc\u30c9\u541b": "CLAUDE",
    "\u8abf\u67fb\u54e1S": "InvestigatorS",
}


def normalize_speaker(name: str | None) -> str:
    key = (name or "").strip()
    return SPEAKER_ALIASES.get(key, key)


@lru_cache(maxsize=1)
def get_voice_profiles() -> dict[str, dict[str, Any]]:
    profiles = {k: dict(v) for k, v in DEFAULT_VOICE_PROFILES.items()}
    for name in list(profiles):
        env_name = f"VOICE_PROFILE_{name.upper()}"
        raw = os.getenv(env_name)
        if not raw:
            continue
        try:
            override = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(override, dict):
            profiles[name].update(override)
    return profiles


def get_voice_profile(name: str | None) -> dict[str, Any] | None:
    speaker = normalize_speaker(name)
    if not speaker:
        return None
    return get_voice_profiles().get(speaker)
