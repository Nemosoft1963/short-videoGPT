import subprocess
from pathlib import Path
from typing import Any

from gtts import gTTS

# gTTS は素のままだと少しもっさりするため、速度を底上げする
DEFAULT_SPEED = 1.15

# 常時かける音質強化フィルタ:
#   highpass=f=80          : こもった低音を除去してクリアに
#   equalizer=f=2500:...   : 2.5kHz付近（子音・明瞭感）を+2.5dBブースト
#   acompressor            : 小声〜大声をならして聴き取りやすく
_ENHANCE_FILTERS = [
    "highpass=f=80",
    "equalizer=f=2500:width_type=o:width=2.0:g=2.5",
    "acompressor=threshold=-20dB:ratio=3:attack=5:release=100:makeup=1.5",
]


def _atempo_chain(speed: float) -> list[str]:
    """atempo フィルタ（有効範囲 0.5–2.0）を必要に応じてチェーンする。"""
    filters = []
    while speed > 2.0:
        filters.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        filters.append("atempo=0.5")
        speed *= 2.0
    filters.append(f"atempo={speed:.4f}")
    return filters


class GTTSClient:
    """Google Translate TTS（gTTS）による音声合成クライアント。APIキー不要・無料。"""

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

        mp3_tmp = out_path.with_suffix(".gtts_tmp.mp3")
        gTTS(text=text, lang="ja").save(str(mp3_tmp))

        # フィルタチェーン: 音質強化 → 速度調整 → 音量
        af_filters = list(_ENHANCE_FILTERS)

        speed = float(speed_scale) if speed_scale is not None else DEFAULT_SPEED
        if abs(speed - 1.0) > 0.01:
            af_filters.extend(_atempo_chain(speed))

        if abs(volume_scale - 1.0) > 0.01:
            af_filters.append(f"volume={volume_scale}")

        cmd = ["ffmpeg", "-y", "-i", str(mp3_tmp), "-af", ",".join(af_filters), str(out_path)]
        subprocess.run(cmd, check=True)
        mp3_tmp.unlink(missing_ok=True)

        # gTTS はフォネームタイミングを返さない → 均等スペースで代替
        return out_path, []

    @staticmethod
    def map_fracs_to_chars(mora_fracs: list, n_chars: int) -> list:
        if not mora_fracs or n_chars <= 0:
            return [i / max(n_chars, 1) for i in range(n_chars)]
        n = len(mora_fracs)
        return [mora_fracs[min(round(i / n_chars * n), n - 1)] for i in range(n_chars)]
