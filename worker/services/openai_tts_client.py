import os
import subprocess
from pathlib import Path

from openai import OpenAI

OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1")

# speaker_id → voice 名のマッピング（UIの選択肢と対応）
VOICE_MAP = {
    0: "alloy",
    1: "echo",
    2: "fable",
    3: "nova",
    4: "onyx",
    5: "shimmer",
}
DEFAULT_VOICE = os.getenv("OPENAI_TTS_VOICE", "nova")


class OpenAITTSClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY が設定されていません（.env に追加してください）")
        self.client = OpenAI(api_key=api_key)

    def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker_id: int = 0,
        speed_scale: float | None = None,
        volume_scale: float = 1.0,
    ) -> tuple[Path, list[float]]:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        voice = VOICE_MAP.get(int(speaker_id), DEFAULT_VOICE)
        # OpenAI TTS speed range: 0.25–4.0
        speed = max(0.25, min(4.0, float(speed_scale or 1.0)))

        response = self.client.audio.speech.create(
            model=OPENAI_TTS_MODEL,
            voice=voice,
            input=text,
            response_format="wav",
            speed=speed,
        )
        response.stream_to_file(str(out_path))

        if abs(volume_scale - 1.0) > 0.01:
            tmp = out_path.with_suffix(".vol_tmp.wav")
            out_path.rename(tmp)
            subprocess.run([
                "ffmpeg", "-y", "-i", str(tmp),
                "-af", f"volume={volume_scale}",
                str(out_path),
            ], check=True)
            tmp.unlink(missing_ok=True)

        # OpenAI TTS はフォネームタイミングを返さない
        # → subtitle_service が mora_fracs=[] を受け取り均等スペースで代替
        return out_path, []

    @staticmethod
    def map_fracs_to_chars(mora_fracs: list[float], n_chars: int) -> list[float]:
        if not mora_fracs or n_chars <= 0:
            return [i / max(n_chars, 1) for i in range(n_chars)]
        n = len(mora_fracs)
        return [mora_fracs[min(round(i / n_chars * n), n - 1)] for i in range(n_chars)]
