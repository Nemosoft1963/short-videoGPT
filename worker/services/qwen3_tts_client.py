import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests

from services.pronunciation import (
    extract_pronunciation_overrides,
    load_pronunciation_map,
    normalize_symbols,
    normalize_text_for_tts,
    number_to_kana,
    replace_numbers_with_kana,
    replace_pronunciation_terms,
)


QWEN3_TTS_URL = os.getenv("QWEN3_TTS_URL", "http://qwen3tts:5005")
DEFAULT_MODEL = os.getenv("QWEN3_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
DEFAULT_MODE = os.getenv("QWEN3_TTS_MODE", "voice_clone")
DEFAULT_LANGUAGE = os.getenv("QWEN3_TTS_LANGUAGE", "Japanese")
DEFAULT_SPEAKER = os.getenv("QWEN3_TTS_SPEAKER", "chikamichi")
DEFAULT_INSTRUCT = os.getenv("QWEN3_TTS_INSTRUCT", "")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("QWEN3_TTS_TIMEOUT_SECONDS", "600"))
DEFAULT_VOLUME_GAIN = float(os.getenv("QWEN3_TTS_VOLUME_GAIN", "1.8"))
MAX_CHARS_PER_REQUEST = int(os.getenv("QWEN3_TTS_MAX_CHARS_PER_REQUEST", "60"))
DEFAULT_SPEED_GAIN = float(os.getenv("QWEN3_TTS_SPEED_GAIN", "1.0"))
CHUNK_PAUSE_SECONDS = float(os.getenv("QWEN3_TTS_CHUNK_PAUSE_SECONDS", "0.02"))
TRIM_CHUNK_SILENCE = os.getenv("QWEN3_TTS_TRIM_CHUNK_SILENCE", "false").lower() not in {"0", "false", "no", "off"}
SILENCE_THRESHOLD_DB = os.getenv("QWEN3_TTS_SILENCE_THRESHOLD_DB", "-45dB")
COMPRESS_LONG_SILENCE = os.getenv("QWEN3_TTS_COMPRESS_LONG_SILENCE", "true").lower() not in {"0", "false", "no", "off"}
LONG_SILENCE_DETECT_SECONDS = float(os.getenv("QWEN3_TTS_LONG_SILENCE_DETECT_SECONDS", "0.24"))
LONG_SILENCE_KEEP_SECONDS = float(os.getenv("QWEN3_TTS_LONG_SILENCE_KEEP_SECONDS", "0.12"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
PRONUNCIATION_MAP_JSON = os.getenv("QWEN3_TTS_PRONUNCIATION_MAP", "")
PRONUNCIATION_MAP_PATH = os.getenv(
    "QWEN3_TTS_PRONUNCIATION_MAP_PATH",
    str(STORAGE_DIR / "config" / "pronunciation_map.json"),
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
    "B2B": "ビートゥービー",
    "VAT": "ブイエーティー",
    "EU": "イーユー",
    "USA": "ユーエスエー",
    "FICA": "ファイカ",
    "Social Security": "ソーシャル セキュリティ",
    "Medicare": "メディケア",
    "人頭税": "じんとうぜい",
    "消費税の闇": "しょうひぜいのやみ",
    "雇用保護": "こようほご",
    "輸出還付": "ゆしゅつかんぷ",
    "借入": "かりいれ",
    "人件費": "じんけんひ",
    "外注費": "がいちゅうひ",
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
    "設計図": "せっけいず",
    "医療崩壊": "いりょうほうかい",
    "訪問介護": "ほうもんかいご",
    "輝いている": "かがやいている",
    "瀬戸際": "せとぎわ",
    "付加価値": "ふかかち",
    "社会保険料": "しゃかいほけんりょう",
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
    "楯": "たて",
}

LANGUAGE_MAP = {
    "JP": "Japanese",
    "JA": "Japanese",
    "JAPANESE": "Japanese",
    "EN": "English",
    "ZH": "Chinese",
    "CN": "Chinese",
    "KO": "Korean",
    "KR": "Korean",
}


class Qwen3TTSClient:
    """HTTP client for an external Qwen3-TTS service.

    The service is intentionally external to avoid changing the existing worker
    runtime. Expected endpoints are compatible with the local wrapper described
    in docs/runbook_qwen3_tts.md:

      POST /voice      -> audio bytes, or JSON with audio_base64/audio_url/path
      GET  /voices     -> optional list of available voices
      GET  /health     -> optional health check
    """

    def __init__(self, base_url: str = QWEN3_TTS_URL):
        self.base_url = base_url.rstrip("/")

    def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker_id: int | None = None,
        speed_scale: float | None = None,
        volume_scale: float = 1.0,
        model_id: int | None = None,
        style: str | None = None,
        style_weight: float | None = None,
        sdp_ratio: float | None = None,
        noise: float | None = None,
        noisew: float | None = None,
        language: str | None = None,
        qwen3_tts_model: str | None = None,
        qwen3_tts_mode: str | None = None,
        qwen3_tts_speaker: str | None = None,
        qwen3_tts_instruct: str | None = None,
        **_: Any,
    ) -> tuple[Path, list[float]]:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_text = self._normalize_text_for_tts(text)
        payload = {
            "text": normalized_text,
            "model": qwen3_tts_model or DEFAULT_MODEL,
            "mode": qwen3_tts_mode or DEFAULT_MODE,
            "speaker": qwen3_tts_speaker or DEFAULT_SPEAKER,
            "speaker_id": speaker_id,
            "language": self._normalize_language(language),
            "instruct": qwen3_tts_instruct if qwen3_tts_instruct is not None else DEFAULT_INSTRUCT,
            "speed_scale": float(speed_scale or 1.0),
            "volume_scale": float(volume_scale),
            "style": style,
            "style_weight": style_weight,
            "sdp_ratio": sdp_ratio,
            "noise": noise,
            "noisew": noisew,
            "output_format": "wav",
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        chunks = self._split_text(normalized_text, MAX_CHARS_PER_REQUEST)
        if len(chunks) <= 1:
            self._request_voice(payload, out_path)
        else:
            with tempfile.TemporaryDirectory(prefix=f"{out_path.stem}_qwen3_", dir=out_path.parent) as tmp_dir:
                chunk_paths = []
                for index, chunk in enumerate(chunks, start=1):
                    chunk_payload = dict(payload)
                    chunk_payload["text"] = chunk
                    chunk_path = Path(tmp_dir) / f"chunk_{index:03d}.wav"
                    self._request_voice(chunk_payload, chunk_path)
                    # Keep this opt-in: aggressive silence trimming can mistake
                    # intentional phrase pauses for trailing silence and cut speech.
                    if TRIM_CHUNK_SILENCE:
                        self._trim_edge_silence(chunk_path)
                    chunk_paths.append(chunk_path)
                self._concat_wavs(chunk_paths, out_path)

        final_tempo = max(0.5, min(2.0, float(speed_scale or 1.0) * DEFAULT_SPEED_GAIN))
        if abs(final_tempo - 1.0) > 0.01:
            self._apply_tempo(out_path, final_tempo)

        if COMPRESS_LONG_SILENCE:
            self._compress_long_silences(out_path)

        final_volume = max(0.05, float(volume_scale) * DEFAULT_VOLUME_GAIN)
        if abs(final_volume - 1.0) > 0.01:
            self._apply_volume(out_path, final_volume)

        # Qwen3-TTS wrappers generally do not expose mora timing, so subtitles
        # use the same even timing fallback as StyleBertVITS2 and Edge TTS.
        return out_path, []

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        raw = (language or DEFAULT_LANGUAGE or "Japanese").strip()
        return LANGUAGE_MAP.get(raw.upper(), raw)

    def _request_voice(self, payload: dict[str, Any], out_path: Path) -> None:
        response = requests.post(f"{self.base_url}/voice", json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code >= 500 and str(payload.get("mode") or "").lower() == "voice_design":
            fallback_payload = dict(payload)
            fallback_payload["mode"] = "voice_clone"
            fallback_payload["instruct"] = (
                f"{fallback_payload.get('instruct', '')} "
                "声質の指定が利用できない場合でも、文脈に合わせて自然で明瞭に発話する。"
            ).strip()
            response = requests.post(f"{self.base_url}/voice", json=fallback_payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        self._write_response_audio(response, out_path)

    @classmethod
    def _normalize_text_for_tts(cls, text: str) -> str:
        return normalize_text_for_tts(text)

    @staticmethod
    def _extract_pronunciation_overrides(text: str) -> tuple[str, dict[str, str]]:
        return extract_pronunciation_overrides(text)

    @staticmethod
    def _load_pronunciation_map() -> dict[str, str]:
        return load_pronunciation_map()

    @classmethod
    def _replace_pronunciation_terms(cls, text: str, extra_map: dict[str, str] | None = None) -> str:
        return replace_pronunciation_terms(text, extra_map)

    @staticmethod
    def _normalize_symbols(text: str) -> str:
        return normalize_symbols(text)

    @staticmethod
    def _number_to_kana(number: int) -> str:
        return number_to_kana(number)

    @classmethod
    def _replace_numbers_with_kana(cls, text: str) -> str:
        return replace_numbers_with_kana(text)

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return [""]
        if max_chars <= 0 or len(text) <= max_chars:
            return [text]

        parts = [p.strip() for p in re.split(r"(?<=[\u3002\u3001\uff01\uff1f!?\.])", text) if p.strip()]
        if not parts:
            parts = [text]

        chunks: list[str] = []
        current = ""
        for part in parts:
            if len(part) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(Qwen3TTSClient._split_long_text(part, max_chars))
                continue
            candidate = part if not current else f"{current} {part}"
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = part
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks or [text]

    @staticmethod
    def _split_long_text(text: str, max_chars: int) -> list[str]:
        units = [p.strip() for p in re.split(r"(?<=[\u3001,;；:：])", text) if p.strip()]
        if len(units) <= 1:
            return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

        chunks: list[str] = []
        current = ""
        for unit in units:
            if len(unit) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(unit[i:i + max_chars] for i in range(0, len(unit), max_chars))
                continue
            candidate = unit if not current else f"{current} {unit}"
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = unit
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _write_response_audio(self, response: requests.Response, out_path: Path) -> None:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" not in content_type:
            out_path.write_bytes(response.content)
            return

        data = response.json()
        if "audio_base64" in data:
            out_path.write_bytes(base64.b64decode(data["audio_base64"]))
            return
        if "audio_url" in data:
            audio = requests.get(data["audio_url"], timeout=REQUEST_TIMEOUT_SECONDS)
            audio.raise_for_status()
            out_path.write_bytes(audio.content)
            return
        if "path" in data:
            source = Path(data["path"])
            out_path.write_bytes(source.read_bytes())
            return
        raise RuntimeError("Qwen3-TTS response did not include audio bytes, audio_base64, audio_url, or path")

    @staticmethod
    def _concat_wavs(paths: list[Path], out_path: Path) -> None:
        list_path = out_path.with_suffix(".qwen3_chunks.txt")
        silence_path = out_path.with_suffix(".qwen3_chunk_pause.wav")
        normalized_paths = [path.with_suffix(".qwen3_norm.wav") for path in paths]
        try:
            for source, normalized in zip(paths, normalized_paths, strict=True):
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", str(source),
                    "-ar", "44100",
                    "-ac", "2",
                    "-acodec", "pcm_s16le",
                    str(normalized),
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            lines: list[str] = []
            if CHUNK_PAUSE_SECONDS > 0 and len(paths) > 1:
                subprocess.run([
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{CHUNK_PAUSE_SECONDS:.3f}",
                    "-acodec", "pcm_s16le",
                    str(silence_path),
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for index, path in enumerate(normalized_paths):
                lines.append(f"file '{path.as_posix()}'")
                if CHUNK_PAUSE_SECONDS > 0 and len(paths) > 1 and index < len(paths) - 1:
                    lines.append(f"file '{silence_path.as_posix()}'")
            list_path.write_text("\n".join(lines), encoding="utf-8")
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-ar", "44100",
                "-ac", "2",
                str(out_path),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            list_path.unlink(missing_ok=True)
            silence_path.unlink(missing_ok=True)
            for path in normalized_paths:
                path.unlink(missing_ok=True)

    @staticmethod
    def _apply_tempo(path: Path, tempo: float) -> None:
        tmp = path.with_suffix(".qwen3_tempo_tmp.wav")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(path),
            "-filter:a", f"atempo={tempo:.6f}",
            str(tmp),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tmp.replace(path)

    @staticmethod
    def _apply_volume(path: Path, volume: float) -> None:
        tmp = path.with_suffix(".qwen3_volume_tmp.wav")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(path),
            "-af", f"volume={volume},alimiter=limit=0.95",
            str(tmp),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tmp.replace(path)

    @staticmethod
    def _compress_long_silences(path: Path) -> None:
        if LONG_SILENCE_DETECT_SECONDS <= 0 or LONG_SILENCE_KEEP_SECONDS < 0:
            return
        tmp = path.with_suffix(".qwen3_pause_tmp.wav")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(path),
            "-af",
            (
                "silenceremove="
                f"start_periods=1:start_duration=0:start_threshold={SILENCE_THRESHOLD_DB}:"
                f"stop_periods=-1:stop_duration={LONG_SILENCE_DETECT_SECONDS:.3f}:"
                f"stop_threshold={SILENCE_THRESHOLD_DB}:stop_silence={LONG_SILENCE_KEEP_SECONDS:.3f}:"
                "detection=peak"
            ),
            "-ar", "44100",
            "-ac", "2",
            str(tmp),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if tmp.exists() and tmp.stat().st_size > 44:
            tmp.replace(path)
        else:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _trim_edge_silence(path: Path) -> None:
        tmp = path.with_suffix(".qwen3_trim_tmp.wav")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(path),
            "-af",
            (
                f"silenceremove=start_periods=1:start_duration=0.05:start_threshold={SILENCE_THRESHOLD_DB}:"
                f"stop_periods=1:stop_duration=0.12:stop_threshold={SILENCE_THRESHOLD_DB}"
            ),
            "-ar", "44100",
            "-ac", "2",
            str(tmp),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tmp.replace(path)
