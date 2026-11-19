# STT — audio to text

Standalone internal FastAPI service for `glaukOS/backend/stt`.
One audio file in, one JSON object out. No report metadata, database,
translation, MQTT publishing, recording UI, or persistent audio storage.

## API contract

`POST /transcribe`, `multipart/form-data`, required field: `file`.
Successful response (HTTP 200) contains exactly:

```json
{"text": "Ciśnienie pompy wynosi jeden przecinek osiem bara."}
```

Language is detected automatically; the text stays in the spoken language.
No language, department, user, location or report ID is required or returned.
Silence/no recognized speech returns `{"text": ""}`. The caller should ask
for another recording rather than generating a report from empty text.
Errors use standard FastAPI `detail` JSON, not a successful transcript:

| HTTP | Meaning |
| --- | --- |
| 413 | Uploaded audio exceeds 25 MiB |
| 422 | Missing/empty/invalid audio, or duration outside 0.15–120 seconds |
| 503 | Busy (Retry-After: 2) or denoiser unavailable |
| 504 | Audio conversion/denoising timeout |
| 500 | Unexpected inference failure; see container logs |

`GET /health` returns `{"status":"ready"}` after startup loads the model.
It is a liveness/readiness endpoint, not a per-request GPU inference test.
OpenAPI docs are at `/docs`; there is no custom webpage at `/`.

## Start with Docker Desktop + NVIDIA GPU

Run from this folder in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose build stt
docker compose run --rm --no-deps stt python download_models.py
docker compose up -d stt
docker compose logs -f --tail=50 stt
```

Download requires Internet; normal transcription uses local models offline.
The downloader follows `WHISPER_MODEL` via Compose's `MODEL_NAME`; an explicit
`--model large-v3-turbo` is also supported. Change `.env` to the same model before
starting the service. `--revision <HF commit>` pins a download; a manifest records
the resolved model revision and the DeepFilterNet checksum in the model directory.

To reuse Mateusz's existing models without copying/downloading them, before
the Docker commands set this in `.env` and skip the download command:

```dotenv
STT_MODELS_DIR=C:/all/hackathon/ship-stt/models
```

Required: `whisper-large-v3/` with the downloaded model files, plus
`DeepFilterNet3_onnx.tar.gz`. Only paths go into `.env`; do not commit `.env`.
Port defaults to `8001` to avoid the earlier prototype on `8000`.
Stop the old STT container before running this one to release its GPU memory:

```powershell
docker compose -f C:/all/hackathon/ship-stt/compose.yaml stop stt
```

Test from the host (replace the audio path):

```powershell
curl.exe -f http://localhost:8001/health
curl.exe -f -X POST http://localhost:8001/transcribe -F "file=@C:/path/report.wav"
```

Supported inputs include WAV, MP3, WebM/Opus, OGG and M4A/MP4 with an audio track.
FFmpeg decodes them to mono 48 kHz; DeepFilterNet3 denoises; faster-whisper
resamples for Whisper and transcribes with full large-v3, CUDA, float16.
`DENOISE=false` disables denoising globally; it is not a request field.
If GPU memory is insufficient, set `COMPUTE_TYPE=int8_float16` and recreate
with `docker compose up -d stt`. Use one Uvicorn worker and one in-flight
transcription; retries/queueing belong to the caller.

## Backend integration

The main backend sends the audio file to this service and reads `response["text"]`.
For a Python async caller (httpx is a dependency of the caller, not STT):

```python
import httpx

async def transcribe_audio(audio_path, stt_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(audio_path, "rb") as audio:
            response = await client.post(
                f"{stt_url}/transcribe",
                files={"file": ("recording", audio, "application/octet-stream")},
            )
        response.raise_for_status()
        return response.json()["text"]
```

When both services share a Docker Compose network, use `http://stt:8000`.
The standalone Compose here creates its own network: separate Compose projects
do not automatically share DNS. When moving the service into the project's root
Compose, set build context to `./backend/stt` and adjust the model mount path;
no published host port is needed for backend-to-STT traffic on that network.
Do not send a browser directly to localhost on the deployed user's device.
This internal prototype has no authentication; keep it on a trusted internal
network. Apply total request-size limits at the backend/proxy as well: FastAPI
parses multipart uploads before the endpoint checks the audio file size.

The existing frontend `TranscribedPayload` includes both `text` and `lang`.
This STT API deliberately returns only `text` as requested; it is not that MQTT
event payload. The backend/team must decide how to populate `lang` or revise
the event contract. STT does not invent a language field or emit events.
The repository root README still lists `speech/`; update that row to
`backend/stt/` when integrating.

## What belongs in Git

Commit only this folder's source, Docker/config files, `.env.example` and README.
`.gitignore` excludes models, audio, results, local config and caches.
`.dockerignore` includes only runtime source and dependencies in the image.
Do not copy the old prototype webpage, batch evaluator, recordings or weights.
Keep any speech-quality evaluation set separately. Compare real recordings,
short replies and noisy clips again: automatic language detection and removal
of department prompts differ from tests that explicitly selected a language.

PyAV is pinned to 18.1.0 because PyAV 19 removed `metadata_errors`, which
faster-whisper 1.2.1 still passes. Preserve this pin when rebuilding.
