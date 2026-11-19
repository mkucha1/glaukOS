#!/usr/bin/env bash
# Backend statku na Macu dla strony na Supabase (frontend z main, VITE_BACKEND=supabase):
#   telefon/strona -> Storage + report.recorded -> [ten skrypt] -> report.transcribed + report.structured
#
# Uruchamia (wszystko lokalnie, modele na Macu):
#   1. STT zespołu (gałąź stt) jako serwis HTTP na :8002 — Whisper na CPU (int8), bez odszumiania
#   2. Basal (MLX) na :8001
#   3. worker: co 2 s pyta Supabase o nowe nagrania, przepuszcza je przez STT -> qwen (Ollama) -> Basal
#      i dopisuje zdarzenia. Na starcie wyłącza ship_status.autopilot (scenariusz demo w bazie), po Ctrl+C
#      włącza go z powrotem — patrz supabase/README.md.
#
# Wymaga w backend/decision/.env:  SUPABASE_URL i SUPABASE_SECRET_KEY (klucz secret / service role).
# Foldery obok glaukOS w ~/Documents/mari:  stt/ (gałąź stt), moj-llm/ (gałąź moj-llm), .venv-mlx (Basal).
#
# Użycie (z backend/decision):   ENV_DIR=../../../.venv-mlx ./scripts/ship_backend_mac.sh
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f .env ]] && { set -a; source .env; set +a; }
MARI="${MARI:-$(cd ../../.. && pwd)}"
ENV_DIR="${ENV_DIR:-.venv-mlx}"
STT_ENV="${STT_ENV:-$MARI/.venv-stt}"
STT_DIR="${STT_DIR:-$MARI/stt/stt}"
LLM_DIR="${LLM_DIR:-$MARI/moj-llm/my_folder}"
MODELS_DIR="${MODELS_DIR:-$MARI/models}"
WHISPER="${WHISPER:-large-v3}"
STT_PORT="${STT_PORT:-8002}"
PORT="${BASAL_PORT:-8001}"
MODEL="${MODEL:-${BASAL_MODEL:-Remek/basal-2.0-4.5B-MLX-8bit}}"
LLM_MODEL="${LLM_MODEL:-qwen3.5:4b}"
OLLAMA="${LLM_BASE_URL:-http://localhost:11434/v1}"
mkdir -p results
say() { printf '\n\033[1m>> %s\033[0m\n' "$*"; }

# --- 0. Sprawdzenia -----------------------------------------------------------------------------
[[ -n "${SUPABASE_URL:-}" && -n "${SUPABASE_SECRET_KEY:-}" ]] || {
  echo "Brak SUPABASE_URL / SUPABASE_SECRET_KEY w backend/decision/.env (Supabase: Project Settings -> API Keys)."; exit 1; }
command -v ffmpeg >/dev/null || { echo "Brak ffmpeg: brew install ffmpeg"; exit 1; }
[[ -f "$STT_DIR/app/main.py" ]] || { echo "Brak $STT_DIR (git clone -b stt https://github.com/mkucha1/glaukOS.git stt)"; exit 1; }
[[ -f "$LLM_DIR/przetworz.py" ]] || { echo "Brak $LLM_DIR (gałąź moj-llm)"; exit 1; }
[[ -x "$ENV_DIR/bin/basal-serve" ]] || { echo "Brak środowiska Basala $ENV_DIR (ENV_DIR=../../../.venv-mlx)"; exit 1; }
curl -fs "${OLLAMA%/v1}/api/tags" | grep -q "\"${LLM_MODEL}\"" || { echo "Ollama nie działa albo brak ${LLM_MODEL}: ollama serve / ollama pull ${LLM_MODEL}"; exit 1; }

# --- 1. STT jako serwis (kod zespołu: stt/app/main.py) --------------------------------------------
if [[ ! -x "$STT_ENV/bin/python" ]]; then
  uv venv --python cpython-3.12-macos-aarch64-none "$STT_ENV"
fi
"$STT_ENV/bin/python" -c "import faster_whisper, fastapi, uvicorn, multipart" 2>/dev/null || \
  uv pip install --python "$STT_ENV/bin/python" "faster-whisper==1.2.1" "av<19" "ctranslate2==4.6.0" numpy huggingface-hub \
    "fastapi==0.115.12" "uvicorn==0.34.2" "python-multipart==0.0.20"
"$STT_ENV/bin/python" -c "import sys; sys.path.insert(0, 'scripts'); from pathlib import Path; from stt_batch import ensure_model; ensure_model(Path('$MODELS_DIR'), '$WHISPER')"

PIDS=()
cleanup() { for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

say "Etap 1/3: STT na :${STT_PORT} (Whisper ${WHISPER}, CPU). Log: results/stt_server.log"
( cd "$STT_DIR" && MODEL_PATH="$MODELS_DIR/whisper-$WHISPER" MODEL_NAME="$WHISPER" DEVICE=cpu COMPUTE_TYPE=int8 DENOISE=false \
  HF_HUB_OFFLINE=1 exec "$STT_ENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$STT_PORT" ) >results/stt_server.log 2>&1 &
PIDS+=($!)

# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"
python -c "import fastapi, openai, httpx" 2>/dev/null || uv pip install -r "$LLM_DIR/requirements.txt"
uv pip install -q -e . >/dev/null

say "Etap 2/3: Basal na :${PORT}. Log: results/basal_server_worker.log"
basal-serve --model "$MODEL" --mode mlx --host 127.0.0.1 --port "$PORT" >results/basal_server_worker.log 2>&1 &
PIDS+=($!)

for name in "STT http://127.0.0.1:${STT_PORT}/health" "Basal http://127.0.0.1:${PORT}/health"; do
  set -- $name
  for i in $(seq 1 360); do curl -fs "$2" >/dev/null 2>&1 && break; sleep 5; done
  curl -fs "$2" >/dev/null || { echo "$1 nie wstał — sprawdź logi w results/"; exit 1; }
  echo "   $1 gotowy"
done

say "Etap 3/3: worker (Supabase ${SUPABASE_URL}). Nagraj zgłoszenie na stronie; Ctrl+C kończy."
LLM_MODEL="$LLM_MODEL" shipdec worker --stt-url "http://127.0.0.1:${STT_PORT}" \
  --basal-url "http://127.0.0.1:${PORT}/v1/systemone" --llm-dir "$LLM_DIR" --take-over --restore-autopilot
