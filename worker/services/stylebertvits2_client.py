import os
import re
import subprocess
from pathlib import Path
from typing import Any

import requests

from services.pronunciation import normalize_text_for_tts

STYLEBERTVITS2_URL = os.getenv("STYLEBERTVITS2_URL", "http://stylebertvits2:5000")
DEFAULT_MODEL_ID = int(os.getenv("STYLEBERTVITS2_MODEL_ID", "0"))
DEFAULT_SPEAKER_ID = int(os.getenv("STYLEBERTVITS2_SPEAKER_ID", "0"))
DEFAULT_STYLE = os.getenv("STYLEBERTVITS2_STYLE", "Neutral")
DEFAULT_STYLE_WEIGHT = float(os.getenv("STYLEBERTVITS2_STYLE_WEIGHT", "1.0"))
DEFAULT_SDP_RATIO = float(os.getenv("STYLEBERTVITS2_SDP_RATIO", "0.2"))
DEFAULT_NOISE = float(os.getenv("STYLEBERTVITS2_NOISE", "0.6"))
DEFAULT_NOISEW = float(os.getenv("STYLEBERTVITS2_NOISEW", "0.8"))
DEFAULT_LANGUAGE = os.getenv("STYLEBERTVITS2_LANGUAGE", "JP") or "JP"
GROCK_FALLBACK_MODEL_ID = int(os.getenv("STYLEBERTVITS2_GROCK_FALLBACK_MODEL_ID", "3"))
GROCK_FALLBACK_STYLE_WEIGHT = float(os.getenv("STYLEBERTVITS2_GROCK_FALLBACK_STYLE_WEIGHT", "1.5"))
MAX_CHARS_PER_REQUEST = int(os.getenv("STYLEBERTVITS2_MAX_CHARS_PER_REQUEST", "90"))
CHUNK_PAUSE_SECONDS = float(os.getenv("STYLEBERTVITS2_CHUNK_PAUSE_SECONDS", "0.06"))


def _normalize_language(language: str | None) -> str:
    raw = (language or DEFAULT_LANGUAGE or "JP").strip()
    aliases = {
        "japanese": "JP",
        "ja": "JP",
        "jp": "JP",
        "日本語": "JP",
        "english": "EN",
        "en": "EN",
        "chinese": "ZH",
        "zh": "ZH",
    }
    return aliases.get(raw.lower(), raw)


def _split_text(text: str, max_chars: int) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    max_chars = max(20, int(max_chars))
    parts = []
    current = ""
    for piece in re.split(r"([。！？!?、，,.])", text):
        if not piece:
            continue
        candidate = current + piece
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current.strip():
            parts.append(current.strip())
        current = piece
        while len(current) > max_chars:
            parts.append(current[:max_chars].strip())
            current = current[max_chars:]
    if current.strip():
        parts.append(current.strip())
    return [part for part in parts if part]


def _make_silence(path: Path, duration: float) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(max(0.01, duration)), str(path)
    ], check=True)


def _concat_audio(paths: list[Path], list_path: Path, out_path: Path) -> None:
    list_path.write_text("\n".join(f"file '{p.as_posix()}'" for p in paths), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-ar", "44100", "-ac", "2", str(out_path)
    ], check=True)


class StyleBertVITS2Client:
    """Style-Bert-VITS2 FastAPI server client.

    Expected server:
      python server_fastapi.py --dir model_assets --host 0.0.0.0 --port 5000

    Main endpoints:
      GET/POST /voice
      GET /models/info
      GET /status
    """

    def __init__(self, base_url: str = STYLEBERTVITS2_URL):
        self.base_url = base_url.rstrip("/")
        self._models_info_cache: dict | None = None

    def _safe_style(self, model_id: int, style: str) -> str:
        try:
            if self._models_info_cache is None:
                self._models_info_cache = self.models_info()
            info = self._models_info_cache.get(str(model_id)) or self._models_info_cache.get(model_id) or {}
            styles = set((info.get("style2id") or {}).keys())
            if styles and style not in styles:
                return "Neutral" if "Neutral" in styles else sorted(styles)[0]
        except Exception:
            pass
        return style

    def _model_exists(self, model_id: int) -> bool:
        try:
            if self._models_info_cache is None:
                self._models_info_cache = self.models_info()
            return str(model_id) in self._models_info_cache or model_id in self._models_info_cache
        except Exception:
            return True

    def _apply_model_fallback(self, model_id: int, style_weight: float | None) -> tuple[int, float | None]:
        if model_id == 4 and not self._model_exists(model_id):
            return GROCK_FALLBACK_MODEL_ID, max(
                GROCK_FALLBACK_STYLE_WEIGHT,
                float(DEFAULT_STYLE_WEIGHT if style_weight is None else style_weight),
            )
        return model_id, style_weight

    def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker_id: int = DEFAULT_SPEAKER_ID,
        speed_scale: float | None = None,
        volume_scale: float = 1.0,
        model_id: int | None = None,
        style: str | None = None,
        style_weight: float | None = None,
        sdp_ratio: float | None = None,
        noise: float | None = None,
        noisew: float | None = None,
        language: str | None = None,
        **_: Any,
    ) -> tuple[Path, list[float]]:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_text = normalize_text_for_tts(text)

        requested_model_id = int(DEFAULT_MODEL_ID if model_id is None else model_id)
        resolved_model_id, resolved_style_weight = self._apply_model_fallback(requested_model_id, style_weight)
        resolved_style = self._safe_style(resolved_model_id, style or DEFAULT_STYLE)
        speed = max(0.25, min(4.0, float(speed_scale or 1.0)))
        params = {
            "text": normalized_text,
            "model_id": resolved_model_id,
            "speaker_id": int(speaker_id if speaker_id is not None else DEFAULT_SPEAKER_ID),
            "style": resolved_style,
            "style_weight": float(DEFAULT_STYLE_WEIGHT if resolved_style_weight is None else resolved_style_weight),
            "sdp_ratio": float(DEFAULT_SDP_RATIO if sdp_ratio is None else sdp_ratio),
            "noise": float(DEFAULT_NOISE if noise is None else noise),
            "noisew": float(DEFAULT_NOISEW if noisew is None else noisew),
            "length": round(1.0 / speed, 4),
            "language": _normalize_language(language),
        }

        chunks = _split_text(normalized_text, MAX_CHARS_PER_REQUEST)
        if len(chunks) > 1:
            work_dir = out_path.with_name(f"{out_path.stem}_stylebert_chunks")
            work_dir.mkdir(parents=True, exist_ok=True)
            audio_parts: list[Path] = []
            for idx, chunk in enumerate(chunks, start=1):
                chunk_path = work_dir / f"chunk_{idx:02d}.wav"
                self._request_voice({**params, "text": chunk}, chunk_path)
                audio_parts.append(chunk_path)
                if idx < len(chunks) and CHUNK_PAUSE_SECONDS > 0:
                    pause_path = work_dir / f"pause_{idx:02d}.wav"
                    _make_silence(pause_path, CHUNK_PAUSE_SECONDS)
                    audio_parts.append(pause_path)
            _concat_audio(audio_parts, work_dir / "concat_chunks.txt", out_path)
            return out_path, []

        params["text"] = chunks[0] if chunks else normalized_text
        self._request_voice(params, out_path)
        return out_path, []

    def _request_voice(self, params: dict, out_path: Path) -> None:
        r = requests.post(f"{self.base_url}/voice", params=params, timeout=300)
        r.raise_for_status()
        out_path.write_bytes(r.content)

    def models_info(self) -> dict:
        r = requests.get(f"{self.base_url}/models/info", timeout=10)
        r.raise_for_status()
        return r.json()
