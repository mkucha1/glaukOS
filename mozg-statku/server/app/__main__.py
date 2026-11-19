import os

import uvicorn

from .config import Settings

if __name__ == "__main__":
    s = Settings.from_env()
    reload = os.getenv("RELOAD", "0") == "1"
    # workers=1 obowiązkowo: hub, pipeline i kolejka żyją w pamięci jednego procesu
    uvicorn.run("app.main:create_app", factory=True, host=s.host, port=s.port, reload=reload,
                reload_dirs=["app", "plugins"] if reload else None, workers=1,
                timeout_graceful_shutdown=3, log_level=os.getenv("LOG_LEVEL", "info"))
