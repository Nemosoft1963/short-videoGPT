import os
import json
import uuid
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal

import requests
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STYLEBERTVITS2_URL = os.getenv("STYLEBERTVITS2_URL", "http://stylebertvits2:5000")
QWEN3_TTS_URL = os.getenv("QWEN3_TTS_URL", "http://qwen3tts:5005")
QWEN3_TTS_MODEL = os.getenv("QWEN3_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
QWEN3_TTS_MODE = os.getenv("QWEN3_TTS_MODE", "voice_clone")
QWEN3_TTS_SPEAKER = os.getenv("QWEN3_TTS_SPEAKER", "chikamichi")
QWEN3_TTS_LANGUAGE = os.getenv("QWEN3_TTS_LANGUAGE", "Japanese")
QWEN3_TTS_INSTRUCT = os.getenv("QWEN3_TTS_INSTRUCT", "")
STYLEBERT_DEFAULT_MODEL_ID = int(os.getenv("STYLEBERTVITS2_MODEL_ID", "0"))
STYLEBERT_DEFAULT_SPEAKER_ID = int(os.getenv("STYLEBERTVITS2_SPEAKER_ID", "0"))
STYLEBERT_DEFAULT_STYLE = os.getenv("STYLEBERTVITS2_STYLE", "Neutral")

app = FastAPI(title="Local Short Video Generator", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_conn = Redis.from_url(REDIS_URL)
queue = Queue("video", connection=redis_conn)

class ProjectCreate(BaseModel):
    title: str = Field(default="土地があっても、銀行は貸さない", max_length=120)
    prompt: str = Field(default="中小企業経営者向けに、消費税が資金繰りを圧迫する現実を硬質なドキュメンタリー調で伝える")
    script: Optional[str] = Field(default="", description="任意。入力すると、この台本を優先してシーン分割します。空欄なら自動台本です。")
    format: Literal["short_vertical", "standard_landscape"] = "short_vertical"
    duration: int = Field(default=60, ge=15, le=600)
    short_timing_mode: Literal["fixed_44", "fixed_57", "script"] = Field(
        default="script",
        description="ショートの尺制御。fixed_44 は44秒固定、fixed_57 は57秒固定、script は台本尺を優先。",
    )
    standard_timing_mode: Literal["duration_min", "script_unbounded"] = Field(
        default="script_unbounded",
        description="標準画面の尺制御。duration_min は指定尺以上、script_unbounded は台本に合わせて上限なし。",
    )
    style: Literal[
        "serious_documentary",
        "small_business_awareness",
        "tax_issue",
        "recruiting",
        "product_intro",
    ] = "serious_documentary"
    model: Literal["runway", "luma", "veo_lite", "minimax", "mock"] = "mock"
    tts_engine: str = Field(default=os.getenv("TTS_ENGINE", "stylebertvits2"), max_length=40)
    voice_speaker_id: Optional[int] = STYLEBERT_DEFAULT_SPEAKER_ID
    voice_speed_scale: float = Field(default=1.0, ge=0.75, le=1.40)
    tts_model_id: int = Field(default=STYLEBERT_DEFAULT_MODEL_ID, ge=0, description="StyleBertVITS2 の model_id")
    tts_style: str = Field(default=STYLEBERT_DEFAULT_STYLE, max_length=80, description="StyleBertVITS2 の style 名")
    tts_style_weight: float = Field(default=1.0, ge=0.0, le=5.0, description="StyleBertVITS2 の style_weight")
    tts_sdp_ratio: float = Field(default=0.2, ge=0.0, le=1.0, description="StyleBertVITS2 の SDP/DP mix ratio")
    tts_noise: float = Field(default=0.6, ge=0.0, le=2.0, description="StyleBertVITS2 の noise")
    tts_noisew: float = Field(default=0.8, ge=0.0, le=2.0, description="StyleBertVITS2 の noisew")
    tts_language: Literal["JP", "EN", "ZH"] = "JP"
    qwen3_tts_model: str = Field(default=QWEN3_TTS_MODEL, max_length=180, description="Qwen3-TTS model id or local model path")
    qwen3_tts_mode: Literal["custom_voice", "voice_clone", "voice_design"] = QWEN3_TTS_MODE
    qwen3_tts_speaker: str = Field(default=QWEN3_TTS_SPEAKER, max_length=80, description="Qwen3-TTS speaker or clone profile name")
    qwen3_tts_instruct: str = Field(default=QWEN3_TTS_INSTRUCT, max_length=400, description="Qwen3-TTS voice instruction")
    analystk_lipsync_source_mode: Literal["image", "video", "auto"] = Field(
        default=os.getenv("LIPSYNC_ANALYSTK_SOURCE_MODE", "image"),
        description="AnalystK/Major lip-sync source selector: image, video, or auto",
    )
    analystk_lipsync_source_set: Literal["anime", "real"] = Field(
        default=os.getenv("LIPSYNC_ANALYSTK_SOURCE_SET", "anime"),
        description="AnalystK/Major lip-sync source set: anime or real",
    )
    analystk_lipsync_display_mode: Literal["bottom", "full", "explain_right"] = Field(
        default=os.getenv("LIPSYNC_ANALYSTK_DISPLAY_MODE", "bottom"),
        description="AnalystK/Major lip-sync display mode: bottom overlay, full scene, or standard-video right-side explainer",
    )
    subtitle: bool = True
    subtitle_font_size: int = Field(default=72, ge=36, le=120)
    subtitle_wrap_chars: int = Field(default=14, ge=8, le=28, description="1行あたりの目安文字数。画面からのはみ出し防止に使います。")
    subtitle_max_lines: int = Field(default=3, ge=1, le=5, description="同時表示する字幕の最大行数。超えた分はシーン内で分割表示します。")
    subtitle_position_from_bottom_pct: float = Field(default=40.0, ge=6.0, le=55.0, description="字幕位置。画面下から何%上げるか。40なら下から約4割。")
    head_title: str = Field(default="", max_length=80, description="標準画面生成時、完成動画の冒頭3秒に表示するヘッドタイトル")
    thumbnail_time_seconds: float = Field(default=0.0, ge=0.0, description="完成時に切り出すサムネイル位置（秒）")
    final_call_text: str = Field(default="チャンネル登録よろしくね", max_length=120, description="完成動画の最後に表示する最終コール文字")
    final_call_speech: str = Field(default="チャンネル登録よろしくね", max_length=200, description="GMNが読み上げる最終コール発話")
    narration_volume: float = Field(default=1.0, ge=0.3, le=2.0, description="ナレーション音量。1.0が標準、2.0で2倍。")
    bgm: bool = False
    bgm_auto: bool = True
    bgm_filename: str = Field(default="", description="アップロード済みBGMのファイル名。空欄なら自動選択または従来BGM。")
    logo_filename: str = Field(default="", description="アップロード済みロゴのファイル名。空欄ならロゴなし。")
    background_video_filename: str = Field(default="", description="本編で生成映像以外のシーンに使う背景動画")
    intro_video_filename: str = Field(default="", description="完成動画の前に連結する既成動画")
    outro_video_filename: str = Field(default="", description="完成動画の後に連結する既成動画")
    typewriter_subtitle: bool = True

class GenerateResponse(BaseModel):
    project_id: str
    status: str
    status_url: str
    download_url: str

GTTS_VOICES = [
    {"speaker_id": 0, "name": "Google TTS 日本語（標準）"},
]

EDGE_VOICES = [
    {"speaker_id": 0, "name": "Naoki（男性・落ち着き）★ドキュメンタリー向き"},
    {"speaker_id": 1, "name": "Nanami（女性・明るめ）"},
    {"speaker_id": 2, "name": "Keita（男性・標準）"},
    {"speaker_id": 3, "name": "Mayu（女性・穏やか）"},
    {"speaker_id": 4, "name": "Shiori（女性・はっきり）"},
]

STYLEBERT_FALLBACK_VOICES = [
    {"speaker_id": 0, "name": "StyleBertVITS2 speaker 0"},
]

QWEN3_TTS_FALLBACK_VOICES = [
    {
        "speaker_id": 0,
        "speaker": QWEN3_TTS_SPEAKER,
        "name": f"Qwen3-TTS / {QWEN3_TTS_SPEAKER}",
        "tts_engine": "qwen3tts",
        "qwen3_tts_model": QWEN3_TTS_MODEL,
        "qwen3_tts_mode": QWEN3_TTS_MODE,
        "qwen3_tts_language": QWEN3_TTS_LANGUAGE,
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(project_id: str) -> Path:
    return STORAGE_DIR / "projects" / project_id


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _active_project_ids() -> set[str]:
    """Return project ids that are actually being processed by a live RQ worker."""
    active = set()
    try:
        from rq import Worker
        from rq.job import Job

        for worker in Worker.all(connection=redis_conn):
            job_id = worker.get_current_job_id()
            if not job_id:
                continue
            try:
                job = Job.fetch(job_id, connection=redis_conn)
            except Exception:
                continue
            if job.func_name == "tasks.generate_video" and job.args:
                active.add(str(job.args[0]))
    except Exception:
        pass
    return active


LOGO_DIR = STORAGE_DIR / "assets" / "logos"
BGM_DIR = STORAGE_DIR / "assets" / "bgm"
BUMPER_DIR = STORAGE_DIR / "assets" / "bumpers"
FINAL_CALL_DIR = STORAGE_DIR / "assets" / "final_calls"


@app.get("/api/health")
def health():
    return {"ok": True, "time": now_iso()}


@app.post("/api/assets/logo")
async def upload_logo(file: UploadFile = File(...)):
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    filename = file.filename.replace(" ", "_")
    save_path = LOGO_DIR / filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": filename, "path": str(save_path)}


@app.get("/api/assets/logos")
def list_logos():
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    logos = [f.name for f in LOGO_DIR.iterdir() if f.suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}]
    return {"logos": logos}


def _safe_asset_filename(filename: str, fallback: str) -> str:
    raw_name = (filename or fallback).replace(" ", "_")
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw_name)
    return safe_name or fallback


@app.post("/api/assets/bgm")
async def upload_bgm(file: UploadFile = File(...)):
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
        raise HTTPException(status_code=422, detail="mp3 / wav / m4a / aac / ogg / flac の音声ファイルを指定してください")
    filename = _safe_asset_filename(file.filename or f"bgm_{uuid.uuid4().hex[:8]}{suffix}", f"bgm_{uuid.uuid4().hex[:8]}.mp3")
    save_path = BGM_DIR / filename
    if save_path.exists():
        filename = f"{save_path.stem}_{uuid.uuid4().hex[:8]}{suffix}"
        save_path = BGM_DIR / filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": filename, "path": str(save_path)}


@app.get("/api/assets/bgms")
def list_bgms():
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    bgms = [f.name for f in BGM_DIR.iterdir() if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}]
    return {"bgms": sorted(bgms)}


@app.post("/api/assets/bumper")
async def upload_bumper(file: UploadFile = File(...)):
    BUMPER_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v", ".webm"}:
        raise HTTPException(status_code=422, detail="mp4 / mov / m4v / webm の動画ファイルを指定してください")
    filename = _safe_asset_filename(file.filename or f"bumper_{uuid.uuid4().hex[:8]}.mp4", f"bumper_{uuid.uuid4().hex[:8]}.mp4")
    save_path = BUMPER_DIR / filename
    if save_path.exists():
        filename = f"{save_path.stem}_{uuid.uuid4().hex[:8]}{suffix}"
        save_path = BUMPER_DIR / filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": filename, "path": str(save_path)}


@app.get("/api/assets/bumpers")
def list_bumpers():
    BUMPER_DIR.mkdir(parents=True, exist_ok=True)
    bumpers = [f.name for f in BUMPER_DIR.iterdir() if f.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}]
    return {"bumpers": bumpers}


@app.get("/api/assets/final-calls")
def list_final_calls():
    FINAL_CALL_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for meta in sorted(FINAL_CALL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = read_json(meta, {})
        clip = FINAL_CALL_DIR / f"{meta.stem}.mp4"
        items.append({
            "key": meta.stem,
            "text": data.get("text", ""),
            "speech": data.get("speech", ""),
            "duration": data.get("duration"),
            "exists": clip.exists(),
            "updated_at": datetime.fromtimestamp(meta.stat().st_mtime, timezone.utc).isoformat(),
        })
    return {"final_calls": items}


@app.get("/api/voices")
def list_voices():
    """TTS_ENGINE に応じて利用可能な話者一覧を返します。"""
    engine = os.getenv("TTS_ENGINE", "stylebertvits2").lower()
    if engine in ("stylebertvits2", "style-bert-vits2", "sbv2"):
        try:
            res = requests.get(f"{STYLEBERTVITS2_URL.rstrip('/')}/models/info", timeout=5)
            res.raise_for_status()
            models = res.json()
            voices = []
            styles_by_model = {}
            for model_id, info in models.items():
                id2spk = info.get("id2spk") or {}
                spk2id = info.get("spk2id") or {}
                style2id = info.get("style2id") or {}
                styles_by_model[str(model_id)] = sorted(style2id.keys()) or ["Neutral"]
                if id2spk:
                    for sid, name in id2spk.items():
                        voices.append({
                            "speaker_id": int(sid),
                            "name": f"SBV2 model {model_id} / {name}",
                            "model_id": int(model_id),
                            "tts_engine": "stylebertvits2",
                        })
                else:
                    for name, sid in spk2id.items():
                        voices.append({
                            "speaker_id": int(sid),
                            "name": f"SBV2 model {model_id} / {name}",
                            "model_id": int(model_id),
                            "tts_engine": "stylebertvits2",
                        })
            voices.sort(key=lambda voice: 0 if voice.get("model_id") == STYLEBERT_DEFAULT_MODEL_ID else 1)
            return {
                "voices": voices or STYLEBERT_FALLBACK_VOICES,
                "source": "stylebertvits2",
                "models": models,
                "styles_by_model": styles_by_model,
                "default_model_id": STYLEBERT_DEFAULT_MODEL_ID,
                "default_speaker_id": STYLEBERT_DEFAULT_SPEAKER_ID,
                "default_style": STYLEBERT_DEFAULT_STYLE,
            }
        except Exception:
            return {"voices": STYLEBERT_FALLBACK_VOICES, "source": "stylebertvits2-fallback"}
    if engine in ("qwen3tts", "qwen3-tts", "qwen"):
        try:
            res = requests.get(f"{QWEN3_TTS_URL.rstrip('/')}/voices", timeout=5)
            res.raise_for_status()
            data = res.json()
            voices = data.get("voices", data if isinstance(data, list) else [])
            normalized = []
            for index, voice in enumerate(voices):
                if not isinstance(voice, dict):
                    continue
                speaker = voice.get("speaker") or voice.get("id") or voice.get("name") or QWEN3_TTS_SPEAKER
                normalized.append({
                    "speaker_id": int(voice.get("speaker_id", index)),
                    "speaker": str(speaker),
                    "name": voice.get("name") or f"Qwen3-TTS / {speaker}",
                    "tts_engine": "qwen3tts",
                    "qwen3_tts_model": voice.get("model") or voice.get("qwen3_tts_model") or QWEN3_TTS_MODEL,
                    "qwen3_tts_mode": voice.get("mode") or voice.get("qwen3_tts_mode") or QWEN3_TTS_MODE,
                    "qwen3_tts_language": voice.get("language") or voice.get("qwen3_tts_language") or QWEN3_TTS_LANGUAGE,
                })
            return {
                "voices": normalized or QWEN3_TTS_FALLBACK_VOICES,
                "source": "qwen3tts",
                "default_speaker": QWEN3_TTS_SPEAKER,
                "default_model": QWEN3_TTS_MODEL,
                "default_mode": QWEN3_TTS_MODE,
                "default_language": QWEN3_TTS_LANGUAGE,
                "default_instruct": QWEN3_TTS_INSTRUCT,
            }
        except Exception:
            return {
                "voices": QWEN3_TTS_FALLBACK_VOICES,
                "source": "qwen3tts-fallback",
                "default_speaker": QWEN3_TTS_SPEAKER,
                "default_model": QWEN3_TTS_MODEL,
                "default_mode": QWEN3_TTS_MODE,
                "default_language": QWEN3_TTS_LANGUAGE,
                "default_instruct": QWEN3_TTS_INSTRUCT,
            }
    if engine == "edge":
        return {"voices": EDGE_VOICES, "source": "edge"}
    if engine == "gtts":
        return {"voices": GTTS_VOICES, "source": "gtts"}
    return {"voices": EDGE_VOICES, "source": "edge-fallback"}



@app.get("/api/diagnostics")
def diagnostics():
    """ローカル構成の疎通確認。生成に失敗した時の切り分け用です。"""
    result = {
        "api": "ok",
        "redis": "unknown",
        "stylebertvits2": "unknown",
        "qwen3tts": "unknown",
        "lipsync": "unknown",
        "runway": "unknown",
        "storage_dir": str(STORAGE_DIR),
        "video_engine": os.getenv("VIDEO_ENGINE", "mock"),
    }
    try:
        redis_conn.ping()
        result["redis"] = "ok"
    except Exception as e:
        result["redis"] = f"ng: {e}"
    try:
        r = requests.get(f"{STYLEBERTVITS2_URL.rstrip('/')}/status", timeout=5)
        if r.ok:
            result["stylebertvits2"] = f"ok: {r.text[:120]}"
        else:
            r = requests.get(f"{STYLEBERTVITS2_URL.rstrip('/')}/models/info", timeout=5)
            result["stylebertvits2"] = "ok" if r.ok else f"ng: HTTP {r.status_code}"
    except Exception as e:
        result["stylebertvits2"] = f"ng: {e}"
    try:
        qwen3 = QWEN3_TTS_URL.rstrip("/")
        r = requests.get(f"{qwen3}/health", timeout=5)
        if r.ok:
            result["qwen3tts"] = f"ok: {r.text[:120]}"
        else:
            r = requests.get(f"{qwen3}/voices", timeout=5)
            result["qwen3tts"] = "ok" if r.ok else f"ng: HTTP {r.status_code}"
    except Exception as e:
        result["qwen3tts"] = f"ng: {e}"
    try:
        lipsync = os.getenv("LIPSYNC_URL", "http://lipsync:7860").rstrip("/")
        r = requests.get(f"{lipsync}/health", timeout=5)
        result["lipsync"] = "ok" if r.ok else f"ng: HTTP {r.status_code}"
    except Exception as e:
        result["lipsync"] = f"ng: {e}"
    # Runway キャッシュ状況
    cache_dir = STORAGE_DIR / "assets" / "runway_cache"
    if cache_dir.exists():
        cached = list(cache_dir.glob("*.jpg"))
        result["runway_cache"] = f"{len(cached)} 枚"
    else:
        result["runway_cache"] = "0 枚"
    # Runway 疎通確認
    runway_key = os.getenv("RUNWAY_API_KEY", "")
    if not runway_key:
        result["runway"] = "ng: RUNWAY_API_KEY 未設定"
    else:
        try:
            r = requests.get(
                "https://api.dev.runwayml.com/v1/tasks",
                headers={
                    "Authorization": f"Bearer {runway_key}",
                    "X-Runway-Version": "2024-11-06",
                },
                params={"limit": 1},
                timeout=8,
            )
            if r.ok:
                result["runway"] = f"ok: HTTP {r.status_code}"
            elif r.status_code == 401:
                result["runway"] = "ng: 認証失敗 (APIキー確認)"
            elif r.status_code == 404:
                result["runway"] = f"ok: key valid (tasks endpoint 404)"
            else:
                result["runway"] = f"ng: HTTP {r.status_code} {r.text[:120]}"
        except Exception as e:
            result["runway"] = f"ng: {e}"
    luma_key = os.getenv("LUMAAI_API_KEY", "") or os.getenv("LUMA_API_KEY", "")
    if not luma_key:
        result["luma"] = "ng: LUMAAI_API_KEY or LUMA_API_KEY is not set"
    else:
        try:
            luma_base = os.getenv("LUMA_API_BASE", "https://api.lumalabs.ai/dream-machine/v1").rstrip("/")
            r = requests.get(
                f"{luma_base}/generations",
                headers={
                    "Authorization": f"Bearer {luma_key}",
                    "Accept": "application/json",
                },
                params={"limit": 1},
                timeout=8,
            )
            if r.ok:
                result["luma"] = f"ok: HTTP {r.status_code}"
            elif r.status_code == 401:
                result["luma"] = "ng: auth failed"
            else:
                result["luma"] = f"ng: HTTP {r.status_code} {r.text[:120]}"
        except Exception as e:
            result["luma"] = f"ng: {e}"
    minimax_key = os.getenv("MINIMAX_API_KEY", "")
    result["minimax"] = "unknown"
    if not minimax_key:
        result["minimax"] = "ng: MINIMAX_API_KEY is not set"
    else:
        try:
            minimax_base = os.getenv("MINIMAX_API_BASE", "https://api.minimax.io/v1").rstrip("/")
            r = requests.get(
                f"{minimax_base}/query/video_generation",
                headers={"Authorization": f"Bearer {minimax_key}"},
                params={"task_id": "0"},
                timeout=8,
            )
            if r.status_code in (401, 403):
                result["minimax"] = "ng: auth failed"
            elif r.status_code < 500:
                result["minimax"] = f"ok: HTTP {r.status_code}"
            else:
                result["minimax"] = f"ng: HTTP {r.status_code} {r.text[:120]}"
        except Exception as e:
            result["minimax"] = f"ng: {e}"
    gemini_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    result["veo_lite"] = "unknown"
    if not gemini_key:
        result["veo_lite"] = "ng: GEMINI_API_KEY or GOOGLE_API_KEY is not set"
    else:
        try:
            veo_base = os.getenv("VEO_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
            veo_model = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")
            r = requests.get(
                f"{veo_base}/models/{veo_model}",
                headers={"x-goog-api-key": gemini_key},
                timeout=8,
            )
            if r.ok:
                result["veo_lite"] = f"ok: HTTP {r.status_code}"
            elif r.status_code in (401, 403):
                result["veo_lite"] = "ng: auth failed or model unavailable"
            else:
                result["veo_lite"] = f"ng: HTTP {r.status_code} {r.text[:120]}"
        except Exception as e:
            result["veo_lite"] = f"ng: {e}"
    return result


@app.post("/api/projects", response_model=GenerateResponse)
def create_project(payload: ProjectCreate):
    if payload.format == "standard_landscape" and payload.standard_timing_mode != "script_unbounded" and payload.duration > 600:
        raise HTTPException(status_code=422, detail="standard_landscape は最大 600 秒まで指定できます")

    project_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    pdir = project_dir(project_id)
    pdir.mkdir(parents=True, exist_ok=True)

    project = payload.model_dump()
    project.update({
        "project_id": project_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    write_json(pdir / "project.json", project)
    write_json(pdir / "status.json", {
        "project_id": project_id,
        "status": "queued",
        "progress": 0,
        "message": "生成キューに登録しました",
        "updated_at": now_iso(),
    })

    try:
        job = queue.enqueue("tasks.generate_video", project_id, job_timeout="24h")
        write_json(pdir / "status.json", {
            "project_id": project_id,
            "status": "queued",
            "progress": 0,
            "message": "生成キューに登録しました",
            "job_id": job.id,
            "updated_at": now_iso(),
        })
    except Exception as e:
        write_json(pdir / "status.json", {
            "project_id": project_id,
            "status": "failed",
            "progress": 100,
            "message": f"生成キュー登録に失敗しました: {e}",
            "error": repr(e),
            "updated_at": now_iso(),
        })
        raise HTTPException(status_code=500, detail=f"生成キュー登録に失敗しました。Redis/API/workerを確認してください: {e}")

    return GenerateResponse(
        project_id=project_id,
        status="queued",
        status_url=f"/api/projects/{project_id}/status",
        download_url=f"/api/projects/{project_id}/download",
    )


@app.get("/api/projects/{project_id}/status")
def get_status(project_id: str):
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="project not found")
    return read_json(pdir / "status.json", {"status": "unknown"})


@app.post("/api/projects/{project_id}/cancel")
def cancel_project(project_id: str):
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="project not found")

    status_data = read_json(pdir / "status.json", {})
    current = status_data.get("status", "")
    if current == "cancelling":
        (pdir / "cancel.flag").unlink(missing_ok=True)
        write_json(pdir / "status.json", {
            **status_data,
            "status": "cancelled",
            "progress": 0,
            "message": "ジョブは動作していないため、中断済みにしました",
            "updated_at": now_iso(),
        })
        return {"ok": True, "message": "中断済みにしました"}
    if current in ("completed", "failed", "cancelled"):
        return {"ok": False, "message": f"中断できません（状態: {current}）"}

    # キャンセルフラグファイルを書く（workerが検知して停止する）
    (pdir / "cancel.flag").write_text("1", encoding="utf-8")

    # キュー待ち中のジョブはRQ経由で即時削除
    (pdir / "cancel.flag").write_text("1", encoding="utf-8")

    job_id = status_data.get("job_id")
    if job_id:
        try:
            from rq.job import Job
            job = Job.fetch(job_id, connection=redis_conn)
            job.cancel()
        except Exception:
            pass

    write_json(pdir / "status.json", {
        **status_data,
        "status": "cancelling",
        "message": "中断リクエストを受け付けました",
        "updated_at": now_iso(),
    })
    return {"ok": True, "message": "中断リクエストを送信しました"}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="project not found")
    return read_json(pdir / "project.json", {})


@app.get("/api/projects/{project_id}/scenes")
def get_scenes(project_id: str):
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="project not found")
    return read_json(pdir / "scenes.json", {"scenes": []})


@app.get("/api/projects/{project_id}/download")
def download(project_id: str):
    final = project_dir(project_id) / "final" / "final.mp4"
    if not final.exists():
        raise HTTPException(status_code=404, detail="final video is not ready")
    return FileResponse(path=final, media_type="video/mp4", filename=f"{project_id}.mp4")


@app.get("/api/projects/{project_id}/chapters")
def get_chapters(project_id: str):
    chapters = project_dir(project_id) / "final" / "chapters.txt"
    if not chapters.exists():
        raise HTTPException(status_code=404, detail="chapters are not ready")
    return FileResponse(path=chapters, media_type="text/plain; charset=utf-8", filename=f"{project_id}_chapters.txt")


@app.get("/api/projects/{project_id}/chapters.json")
def get_chapters_json(project_id: str):
    chapters = project_dir(project_id) / "final" / "chapters.json"
    if not chapters.exists():
        raise HTTPException(status_code=404, detail="chapters are not ready")
    return read_json(chapters, {"chapters": []})


def _extract_thumbnail_file(project_id: str, at_seconds: float) -> Path:
    final_dir = project_dir(project_id) / "final"
    final = final_dir / "final.mp4"
    if not final.exists():
        raise HTTPException(status_code=404, detail="final video is not ready")
    at_seconds = max(0.0, float(at_seconds or 0.0))
    suffix = str(at_seconds).replace(".", "_")
    thumb = final_dir / f"thumbnail_{suffix}.jpg"
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", f"{at_seconds:.3f}",
        "-i", str(final),
        "-frames:v", "1",
        "-q:v", "2",
        str(thumb),
    ], check=True)
    return thumb


@app.post("/api/projects/{project_id}/thumbnail")
def create_thumbnail(project_id: str, at_seconds: float = 0.0):
    thumb = _extract_thumbnail_file(project_id, at_seconds)
    status = read_json(project_dir(project_id) / "status.json", {})
    write_json(project_dir(project_id) / "status.json", {
        **status,
        "thumbnail_path": str(thumb),
        "thumbnail_time_seconds": at_seconds,
        "updated_at": now_iso(),
    })
    return {"thumbnail_url": f"/api/projects/{project_id}/thumbnail?time={at_seconds}", "path": str(thumb)}


@app.get("/api/projects/{project_id}/thumbnail")
def get_thumbnail(project_id: str, time: Optional[float] = None):
    final_dir = project_dir(project_id) / "final"
    if time is not None:
        thumb = _extract_thumbnail_file(project_id, time)
    else:
        thumb = final_dir / "thumbnail.jpg"
        if not thumb.exists():
            thumb = _extract_thumbnail_file(project_id, 0.0)
    return FileResponse(path=thumb, media_type="image/jpeg", filename=f"{project_id}_thumbnail.jpg")


@app.get("/api/projects")
def list_projects():
    base = STORAGE_DIR / "projects"
    base.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(base.iterdir(), reverse=True):
        if not p.is_dir():
            continue
        project = read_json(p / "project.json", {})
        status = read_json(p / "status.json", {})
        items.append({
            "project_id": p.name,
            "title": project.get("title", p.name),
            "status": status.get("status", "unknown"),
            "progress": status.get("progress", 0),
            "created_at": project.get("created_at"),
        })
    return {"projects": items[:50]}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    pdir = project_dir(project_id)
    base = (STORAGE_DIR / "projects").resolve()
    target = pdir.resolve()
    if base not in target.parents:
        raise HTTPException(status_code=400, detail="invalid project id")
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="project not found")

    status = read_json(pdir / "status.json", {})
    current = status.get("status", "unknown")
    if project_id in _active_project_ids():
        raise HTTPException(status_code=409, detail="実行中の履歴は削除できません。先に中断してください。")

    shutil.rmtree(pdir)
    return {"ok": True, "project_id": project_id}
