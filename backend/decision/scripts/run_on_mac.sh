#!/usr/bin/env bash
# Pierwszy test Basala na Macu z Apple Silicon — przez MLX (GPU Apple), model skwantyzowany do 8 bitów.
# Robi wszystko po kolei: instalacja -> pobranie modelu -> start serwera -> ewaluacja -> zatrzymanie serwera.
# Na podstawie instrukcji z https://github.com/rkinas/basal (v2.8.1, docs/INSTALL.md "Apple Silicon (MLX)").
#
# Użycie (z katalogu projektu):
#   ./scripts/run_on_mac.sh                                      # basal-2.0 4.5B MLX-8bit, 50 zgłoszeń
#   LIMIT=200 ./scripts/run_on_mac.sh                            # cały zbiór
#   MODEL=Remek/basal-2.0-mini-MLX-8bit ./scripts/run_on_mac.sh  # 1.5B, szybszy, dla Maców z 8 GB RAM
#   QUESTIONS=config/questions_moj_wariant.yaml ./scripts/run_on_mac.sh  # inny zestaw pytań
#   DATA=realistic ./scripts/run_on_mac.sh                       # realistyczne, nieczyste wypowiedzi
set -euo pipefail

cd "$(dirname "$0")/.."
# Ustawienia z .env (jeśli jest); zmienne podane w linii poleceń mają pierwszeństwo.
if [[ -f .env ]]; then set -a; source .env; set +a; fi
[[ -n "${HF_TOKEN:-}" ]] || unset HF_TOKEN
MODEL="${MODEL:-${BASAL_MODEL:-Remek/basal-2.0-4.5B-MLX-8bit}}"
LIMIT="${LIMIT:-50}"
PORT="${PORT:-${BASAL_PORT:-8001}}"
ENV_DIR="${ENV_DIR:-.venv-mlx}"
BASAL_VERSION="${BASAL_VERSION:-v2.8.1}"
PY="cpython-3.12-macos-aarch64-none"          # natywny Python arm64 (nie x86_64 pod Rosettą)
QUESTIONS="${QUESTIONS:-${DECISION_QUESTIONS:-config/questions.yaml}}"
DATA="${DATA:-synthetic}"                     # synthetic | realistic
TAG="$(basename "$MODEL")"
QTAG="$(basename "$QUESTIONS" .yaml)"
LOG="results/basal_server_${TAG}.log"
OUT="results/basal_${TAG}.jsonl"
[[ "$QTAG" == "questions" ]] || OUT="results/basal_${TAG}__${QTAG}.jsonl"
[[ "$DATA" == "synthetic" ]] || OUT="${OUT%.jsonl}__${DATA}.jsonl"
mkdir -p results

say() { printf '\n\033[1m>> %s\033[0m\n' "$*"; }

# --- 0. Sprawdzenia -----------------------------------------------------------
[[ "$(uname)" == "Darwin" ]] || { echo "Ten skrypt jest dla macOS. Na Linuksie z GPU: scripts/setup_basal.sh"; exit 1; }
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Terminal działa pod Rosettą (x86_64) albo to nie jest Mac z Apple Silicon. MLX wymaga arm64."
  echo "Otwórz Terminal bez opcji 'Otwórz przy użyciu Rosetty' i spróbuj ponownie."
  exit 1
fi
command -v uv >/dev/null || { echo "Brak uv. Zainstaluj:  curl -LsSf https://astral.sh/uv/install.sh | sh  i otwórz nowy terminal."; exit 1; }

RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
FREE_GB=$(df -g . | awk 'NR==2 {print $4}')
say "RAM: ${RAM_GB} GB, wolne miejsce: ${FREE_GB} GB, model: ${MODEL}"
if [[ "$MODEL" == *4.5B* && $RAM_GB -lt 16 ]]; then
  echo "Uwaga: 4.5B w 8 bitach zajmuje ok. 5-6 GB pamięci. Przy ${RAM_GB} GB RAM może być ciasno."
  echo "Jeśli zabraknie pamięci:  MODEL=Remek/basal-2.0-mini-MLX-8bit ./scripts/run_on_mac.sh"
fi

# --- 1. Środowisko (osobne od .venv z testami, bez torch) ----------------------
if [[ ! -x "$ENV_DIR/bin/basal-serve" ]]; then
  say "Instaluję środowisko MLX (Basal ${BASAL_VERSION} + ten projekt)"
  uv python install "$PY"
  uv venv --python "$PY" --allow-existing "$ENV_DIR"
  # shellcheck disable=SC1091
  source "$ENV_DIR/bin/activate"
  uv pip install "basal[mlx] @ https://github.com/rkinas/basal/archive/refs/tags/${BASAL_VERSION}.tar.gz"
  uv pip install -e ".[dev]"
else
  # shellcheck disable=SC1091
  source "$ENV_DIR/bin/activate"
fi

# --- 2. Dane -------------------------------------------------------------------
if [[ "$DATA" == "realistic" ]]; then
  say "Buduję zbiór realistycznych wypowiedzi"
  shipdec realistic
elif [[ ! -f data/synthetic/labels.jsonl ]]; then
  say "Brak danych — generuję 200 zgłoszeń"
  shipdec generate -n 200
fi

# --- 3. Serwer (pierwszy start pobiera model z Hugging Face) --------------------
say "Startuję serwer Basala (MLX). Pierwszy raz pobiera model — może potrwać. Log: ${LOG}"
basal-serve --model "$MODEL" --mode mlx --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

for i in $(seq 1 360); do                       # do 30 minut (pobieranie + ładowanie)
  if curl -fs "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "Serwer się zatrzymał. Ostatnie linie logu:"; tail -30 "$LOG"; exit 1
  fi
  (( i % 12 == 0 )) && echo "   ...czekam ($((i * 5 / 60)) min)"
  sleep 5
done
curl -fs "http://127.0.0.1:${PORT}/health" >/dev/null || { echo "Serwer nie wstał w 30 minut. Log: $LOG"; exit 1; }
grep -m1 "ready" "$LOG" || true

# --- 4. Ewaluacja --------------------------------------------------------------
say "Ewaluacja: dane ${DATA}, do ${LIMIT} zgłoszeń, pytania: ${QUESTIONS}"
START=$(date +%s)
shipdec evaluate --backend basal --url "http://127.0.0.1:${PORT}/v1/systemone" --limit "$LIMIT" --questions "$QUESTIONS" --data-dir "data/${DATA}" --out "$OUT"
say "Gotowe w $(( $(date +%s) - START )) s. Wyniki: ${OUT} oraz ${OUT%.jsonl}.summary.json"
