from __future__ import annotations

import logging
import os
import sys
import uvicorn

from neuro_mirror.core.settings import Settings
from neuro_mirror.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

if __name__ == "__main__":
    args = sys.argv[1:]
    if "-gpu" in args:
        os.environ["NEURO_MIRROR_DEVICE"] = "cuda"
    elif "-cpu" in args:
        os.environ["NEURO_MIRROR_DEVICE"] = "cpu"

    settings = Settings.from_env()
    logging.getLogger(__name__).info("Device mode: %s", settings.device)
    uvicorn.run(
        create_app(),
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )
