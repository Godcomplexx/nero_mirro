from __future__ import annotations

import logging
import os
import sys
import uvicorn

from neuro_mirror.core.logging_setup import configure_logging
from neuro_mirror.core.settings import Settings
from neuro_mirror.web.app import create_app


# ── CONFIG ───────────────────────────────────────────────────────────────────
# Сохранять WAV-ответы MoCA в runtime/dataset/<session_id>/audio.
# Файлы сохраняются только при наличии согласия профиля на набор данных.
SAVE_MOCA_AUDIO = True


_log_path = configure_logging()

if __name__ == "__main__":
    os.environ["NEURO_MIRROR_SAVE_MOCA_AUDIO"] = "1" if SAVE_MOCA_AUDIO else "0"
    args = sys.argv[1:]
    if "-gpu" in args:
        os.environ["NEURO_MIRROR_DEVICE"] = "cuda"
    elif "-cpu" in args:
        os.environ["NEURO_MIRROR_DEVICE"] = "cpu"

    settings = Settings.from_env()
    logging.getLogger(__name__).info("Device mode: %s", settings.device)
    logging.getLogger(__name__).info("Журнал: %s", _log_path)
    uvicorn.run(
        create_app(),
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )
