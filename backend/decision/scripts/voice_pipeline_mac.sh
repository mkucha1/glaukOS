#!/usr/bin/env bash
# Cały potok na nagraniach: dźwięk -> STT (gałąź stt) -> qwen (gałąź moj-llm) -> Basal (ta gałąź).
#
# Układ folderów (domyślny, obok siebie w ~/Documents/mari):
#   glaukOS/   (ta gałąź)   stt/  (gałąź stt)   moj-llm/  (gałąź moj-llm)   data/  (nagrania)   models/  (Whisper)
#
# Etapy po kolei, żeby modele nie zajmowały pamięci naraz:
#   1. STT: kod zespołu (stt/app/pipeline.py) na CPU Maca — ffmpeg + faster-whisper large-v3 int8
#      (na Macu nie ma CUDA; odszumianie DeepFilterNet domyślnie wyłączone: DENOISE=1 włącza)
#   2. qwen3.5:4b (Ollama) porządkuje tekst
#   3. Basal (MLX) ocenia tekst z STT i tekst po qwenie
# Wynik: backend/decision/results/voice/raport.md (+ JSON na nagranie)
#
# Użycie (z backend/decision):
#   ENV_DIR=../../../.venv-mlx ./scripts/voice_pipeline_mac.sh
#   WHISPER=large-v3-turbo ENV_DIR=../../../.venv-mlx ./scripts/voice_pipeline_mac.sh   # szybszy STT
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
MARI="$(cd ../../.. && pwd)"
ENV_DIR="${ENV_DIR:-.venv-mlx}"
STT_ENV="${STT_ENV:-$MARI/.venv-stt}"
STT_DIR="${STT_DIR:-$MARI/stt/stt}"
LLM_DIR="${LLM_DIR:-$MARI/moj-llm/my_folder}"
AUDIO_DIR="${AUDIO_DIR:-$MARI/data}"
MODELS_DIR="${MODELS_DIR:-$MARI/models}"
WHISPER="${WHISPER:-large-v3}"
MODEL="${MODEL:-${BASAL_MODEL:-Remek/basal-2.0-4.5B-MLX-8bit}}"
PORT="${PORT:-${BASAL_PORT:-8001}}"
LLM_MODEL="${LLM_MODEL:-qwen3.5:4b}"
OLLAMA="${LLM_BASE_URL:-http://localhost:11434/v1}"
OUT="results/voice"
LOG="results/basal_server_voice.log"
mkdir -p "$OUT"

say() { printf '\n\033[1m>> %s\033[0m\n' "$*"; }

# --- 0. Sprawdzenia -------------------------------------------------------------------
command -v ffmpeg >/dev/null || { echo "Brak ffmpeg (STT go używa). Zainstaluj:  brew install ffmpeg"; exit 1; }
command -v uv >/dev/null || { echo "Brak uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
[[ -f "$STT_DIR/app/pipeline.py" ]] || { echo "Brak $STT_DIR. W ~/Documents/mari:  git clone -b stt https://github.com/mkucha1/glaukOS.git stt"; exit 1; }
[[ -f "$LLM_DIR/przetworz.py" ]] || { echo "Brak $LLM_DIR (gałąź moj-llm)."; exit 1; }
[[ -x "$ENV_DIR/bin/basal-serve" ]] || { echo "Brak środowiska Basala $ENV_DIR (ENV_DIR=../../../.venv-mlx)."; exit 1; }
curl -fs "${OLLAMA%/v1}/api/tags" | grep -q "\"${LLM_MODEL}\"" || { echo "Ollama nie działa albo brak ${LLM_MODEL}: ollama serve / ollama pull ${LLM_MODEL}"; exit 1; }
shopt -s nullglob nocaseglob
AUDIO=("$AUDIO_DIR"/*.wav "$AUDIO_DIR"/*.mp3 "$AUDIO_DIR"/*.m4a "$AUDIO_DIR"/*.ogg "$AUDIO_DIR"/*.webm)
shopt -u nocaseglob
(( ${#AUDIO[@]} )) || { echo "Brak nagrań w $AUDIO_DIR"; exit 1; }
say "Nagrania: ${#AUDIO[@]} w $AUDIO_DIR"

# --- 1. STT (osobne środowisko: faster-whisper ma inne zależności niż MLX) -------------
if [[ ! -x "$STT_ENV/bin/python" ]]; then
  say "Tworzę środowisko STT ($STT_ENV)"
  uv venv --python cpython-3.12-macos-aarch64-none "$STT_ENV"
  # jak stt/requirements.txt, bez pakietów CUDA (nvidia-*); PyAV < 19 — patrz stt/README.md
  uv pip install --python "$STT_ENV/bin/python" "faster-whisper==1.2.1" "av<19" "ctranslate2==4.6.0" numpy huggingface-hub
fi
DN=(); [[ "${DENOISE:-0}" == "1" ]] && DN=(--denoise)
say "Etap 1/3: STT (Whisper ${WHISPER}, CPU). Pierwszy raz pobiera model (~3 GB dla large-v3)"
"$STT_ENV/bin/python" scripts/stt_batch.py --stt-dir "$STT_DIR" --models-dir "$MODELS_DIR" --model "$WHISPER" \
  ${DN[@]+"${DN[@]}"} --out "$OUT/stt.jsonl" "${AUDIO[@]}"

# --- 2 i 3. qwen + Basal -----------------------------------------------------------------
# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"
python -c "import fastapi, openai, httpx" 2>/dev/null || uv pip install -r "$LLM_DIR/requirements.txt"
uv pip install -q -e . >/dev/null
say "Startuję Basala (MLX). Log: ${LOG}"
basal-serve --model "$MODEL" --mode mlx --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
for i in $(seq 1 360); do
  curl -fs "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
  kill -0 $SERVER_PID 2>/dev/null || { echo "Basal się zatrzymał:"; tail -30 "$LOG"; exit 1; }
  sleep 5
done
say "Etap 2-3/3: qwen porządkuje tekst, Basal ocenia (tekst z STT i po qwenie)"
LLM_MODEL="$LLM_MODEL" shipdec voice --stt "$OUT/stt.jsonl" --out-dir "$OUT" --llm-dir "$LLM_DIR" \
  --url "http://127.0.0.1:${PORT}/v1/systemone"
say "Gotowe: $OUT/raport.md"
cat "$OUT/raport.md"
