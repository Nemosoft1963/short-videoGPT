# api/main.py または api/routers/ に追加するエンドポイント

from fastapi import APIRouter, UploadFile, File
from pathlib import Path
import os
import shutil

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/storage"))
LOGO_DIR = STORAGE_DIR / "assets" / "logos"

router = APIRouter()

@router.post("/api/assets/logo")
async def upload_logo(file: UploadFile = File(...)):
    """ロゴ画像をアップロードする"""
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    
    # ファイル名を安全に処理
    filename = file.filename.replace(" ", "_")
    save_path = LOGO_DIR / filename
    
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    return {"filename": filename, "path": str(save_path)}

@router.get("/api/assets/logos")
async def list_logos():
    """アップロード済みロゴ一覧を返す"""
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    logos = [f.name for f in LOGO_DIR.iterdir() if f.suffix in ['.png', '.jpg', '.jpeg', '.svg', '.webp']]
    return {"logos": logos}
