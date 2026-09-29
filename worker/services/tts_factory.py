import os

import requests


def _endpoint_available(base_url: str, paths: tuple[str, ...], timeout: float = 2.0) -> bool:
    base = base_url.rstrip("/")
    for path in paths:
        try:
            response = requests.get(f"{base}{path}", timeout=timeout)
            if response.status_code < 500:
                return True
        except requests.RequestException:
            continue
    return False


def _stylebert_available() -> bool:
    base_url = os.getenv("STYLEBERTVITS2_URL", "http://stylebertvits2:5000")
    return _endpoint_available(base_url, ("/status", "/models/info"))


def _qwen3_available() -> bool:
    base_url = os.getenv("QWEN3_TTS_URL", "http://qwen3tts:5005")
    return _endpoint_available(base_url, ("/health", "/voices"))


def _fallback_engine() -> str:
    return os.getenv("TTS_FALLBACK_ENGINE", "qwen3tts").strip().lower().replace("-fallback", "")


def _client_for_available_engine(engine: str):
    """Return a client only when a local HTTP engine is actually reachable."""
    if engine in ("stylebertvits2", "style-bert-vits2", "sbv2"):
        if not _stylebert_available():
            return None
        from services.stylebertvits2_client import StyleBertVITS2Client

        return StyleBertVITS2Client()
    if engine in ("qwen3tts", "qwen3-tts", "qwen"):
        if not _qwen3_available():
            return None
        from services.qwen3_tts_client import Qwen3TTSClient

        return Qwen3TTSClient()
    if engine == "edge":
        from services.edge_tts_client import EdgeTTSClient

        return EdgeTTSClient()
    if engine == "gtts":
        from services.gtts_client import GTTSClient

        return GTTSClient()
    return None


def _fallback_client(unavailable_engine: str):
    # Major/legacy profiles still name StyleBert explicitly. Prefer the active
    # project-wide Qwen bridge for those profiles before using generic voices.
    if unavailable_engine == "StyleBertVITS2" and _qwen3_available():
        print("StyleBertVITS2 is unavailable; falling back to qwen3tts")
        return _client_for_available_engine("qwen3tts")

    fallback = _fallback_engine()
    client = _client_for_available_engine(fallback)
    if client is not None:
        print(f"{unavailable_engine} is unavailable; falling back to {fallback}")
        return client

    # A stopped local fallback bridge should not discard the whole render job.
    if fallback != "edge":
        print(f"{unavailable_engine} and fallback {fallback} are unavailable; falling back to edge")
        return _client_for_available_engine("edge")
    return None


def get_tts_client(engine: str | None = None):
    """TTS_ENGINE 環境変数に応じて適切なクライアントを返す。
    stylebertvits2: Style-Bert-VITS2 FastAPI（ローカル・高品質）
    edge          : Microsoft Edge Neural TTS（無料・高品質）
    gtts          : Google Translate TTS（無料・やや平坦）
    """
    engine = (engine or os.getenv("TTS_ENGINE", "stylebertvits2")).lower().replace("-fallback", "")
    if engine in ("stylebertvits2", "style-bert-vits2", "sbv2"):
        if not _stylebert_available():
            fallback = _fallback_client("StyleBertVITS2")
            if fallback is not None:
                return fallback
        from services.stylebertvits2_client import StyleBertVITS2Client

        return StyleBertVITS2Client()
    if engine in ("qwen3tts", "qwen3-tts", "qwen"):
        if not _qwen3_available():
            fallback = _fallback_client("Qwen3-TTS")
            if fallback is not None:
                return fallback
        from services.qwen3_tts_client import Qwen3TTSClient
        return Qwen3TTSClient()
    if engine == "edge":
        from services.edge_tts_client import EdgeTTSClient
        return EdgeTTSClient()
    if engine == "gtts":
        from services.gtts_client import GTTSClient
        return GTTSClient()
    return _client_for_available_engine("edge")
