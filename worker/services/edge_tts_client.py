import asyncio
import subprocess
from pathlib import Path
from typing import Any

import edge_tts
from edge_tts.exceptions import NoAudioReceived

# speaker_id → Edge TTS 日本語ボイス名
VOICE_MAP = {
    0: "ja-JP-NaokiNeural",    # 男性・落ち着いた（ドキュメンタリー向き）
    1: "ja-JP-NanamiNeural",   # 女性・明るめ
    2: "ja-JP-KeitaNeural",    # 男性・標準
    3: "ja-JP-MayuNeural",     # 女性・穏やか
    4: "ja-JP-ShioriNeural",   # 女性・はっきり
}
DEFAULT_VOICE = "ja-JP-NaokiNeural"


def _speed_to_rate(speed: float) -> str:
    """speed_scale（1.0=等速）を edge-tts の rate 文字列（例: +10%）に変換する。"""
    pct = round((speed - 1.0) * 100)
    return f"+{pct}%" if pct >= 0 else f"{pct}%"


class EdgeTTSClient:
    """Microsoft Edge Neural TTS クライアント。無料・APIキー不要。"""

    def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker_id: int = 0,
        speed_scale: float | None = None,
        volume_scale: float = 1.0,
        **_: Any,
    ) -> tuple[Path, list[float]]:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        voice = VOICE_MAP.get(int(speaker_id), DEFAULT_VOICE)
        rate = _speed_to_rate(float(speed_scale or 1.0))

        # edge-tts は非同期API → asyncio.run で同期呼び出し
        mp3_tmp = out_path.with_suffix(".edge_tmp.mp3")
        asyncio.run(_save(text, voice, rate, mp3_tmp))

        # MP3 → WAV（+ 音量補正）
        af_filters = []
        if abs(volume_scale - 1.0) > 0.01:
            af_filters.append(f"volume={volume_scale}")

        cmd = ["ffmpeg", "-y", "-i", str(mp3_tmp)]
        if af_filters:
            cmd += ["-af", ",".join(af_filters)]
        cmd.append(str(out_path))
        subprocess.run(cmd, check=True)
        mp3_tmp.unlink(missing_ok=True)

        return out_path, []

    @staticmethod
    def map_fracs_to_chars(mora_fracs: list, n_chars: int) -> list:
        if not mora_fracs or n_chars <= 0:
            return [i / max(n_chars, 1) for i in range(n_chars)]
        n = len(mora_fracs)
        return [mora_fracs[min(round(i / n_chars * n), n - 1)] for i in range(n_chars)]


async def _save(text: str, voice: str, rate: str, out_path: Path) -> None:
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(out_path))
            return
        except NoAudioReceived:
            out_path.unlink(missing_ok=True)
            if attempt == 2:
                raise
            await asyncio.sleep(1.0 + attempt)
