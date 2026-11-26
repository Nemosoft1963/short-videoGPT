"""Launch the Style-Bert-VITS2 WebUI beside its already running API server."""

import os
import runpy
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "tools" / "sbv2" / "sbv2" / "Style-Bert-VITS2"
os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))

from style_bert_vits2.nlp.japanese import pyopenjtalk_worker, user_dict  # noqa: E402


_original_update_dict = user_dict.update_dict


def _update_dict_or_reuse_existing() -> None:
    try:
        _original_update_dict()
    except PermissionError:
        compiled_dict = user_dict.compiled_dict_path
        if not compiled_dict.is_file():
            raise
        pyopenjtalk_worker.update_global_jtalk_with_user_dict(str(compiled_dict))


user_dict.update_dict = _update_dict_or_reuse_existing
port = os.getenv("SBV2_UI_PORT", "7862")
sys.argv = [str(APP_DIR / "app.py"), "--host", "127.0.0.1", "--port", port, "--no_autolaunch"]
runpy.run_path(str(APP_DIR / "app.py"), run_name="__main__")
