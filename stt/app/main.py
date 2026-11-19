"""Internal file-to-text HTTP service. Report metadata belongs to the caller."""
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.pipeline import AudioError, Settings, SpeechPipeline

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
cfg = Settings()
inference_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pipeline = SpeechPipeline(cfg)
    log.info("STT ready: %s / %s / %s", cfg.model_name, cfg.device, cfg.compute_type)
    yield
    del app.state.pipeline


app = FastAPI(title="glaukOS STT", version="1.0.0", lifespan=lifespan)


class Transcript(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"status": "ready"}


@app.post("/transcribe", response_model=Transcript)
def transcribe(file: Annotated[UploadFile, File(description="Audio file")]):
    if not inference_lock.acquire(blocking=False):
        file.file.close()
        raise HTTPException(503, "STT busy. Retry later.", headers={"Retry-After": "2"})
    try:
        with TemporaryDirectory(prefix="glaukos-stt-") as directory:
            work = Path(directory)
            source = work / "upload.bin"
            size = 0
            with source.open("wb") as output:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > cfg.max_upload_bytes:
                        raise HTTPException(413, "Audio file exceeds configured size limit.")
                    output.write(chunk)
            if size == 0:
                raise HTTPException(422, "Audio file is empty.")
            return Transcript(text=app.state.pipeline.process(source, work))
    except AudioError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("STT processing failed")
        raise HTTPException(500, "STT processing failed.") from exc
    finally:
        file.file.close()
        inference_lock.release()
