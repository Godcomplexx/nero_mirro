from __future__ import annotations

import uvicorn

from neuro_mirror.core.settings import Settings
from neuro_mirror.web.app import create_app


if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run(
        create_app(),
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )
