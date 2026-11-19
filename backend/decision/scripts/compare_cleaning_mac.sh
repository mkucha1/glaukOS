#!/usr/bin/env bash
# Basal na surowych wypowiedziach vs na tych samych wypowiedziach po oczyszczeniu warstwą LLM z gałęzi moj-llm.
#
# Co robi:
#   1. buduje nasze zbiory: realistyczne (63 nieczyste wypowiedzi) i syntetyczne (N zgłoszeń)
#   2. czyści treść każdego zgłoszenia przez my_folder/przetworz.py (Ollama, qwen3.5:4b) -> data/<zbiór>_clean
#   3. startuje Basala (MLX), ocenia oba warianty na obu zbiorach, zatrzymuje Basala
#   4. drukuje porównanie: trafność każdej decyzji, ile zgłoszeń przechodzi automatycznie, przykłady zmian
#
# Wymaga: folderu z gałęzią moj-llm (domyślnie ~/Documents/mari/moj-llm) i działającej Ollamy z modelem.
#   ollama serve            # jeśli nie działa jako aplikacja
#   ollama pull qwen3.5:4b
#
# Użycie (z backend/decision):
#   ./scripts/compare_cleaning_mac.sh
#   SYNTH=200 ./scripts/compare_cleaning_mac.sh             # więcej syntetycznych
#   LLM_DIR=/inna/ścieżka/my_folder ./scripts/compare_cleaning_mac.sh
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
MODEL="${MODEL:-${BASAL_MODEL:-Remek/basal-2.0-4.5B-MLX-8bit}}"
PORT="${PORT:-${BASAL_PORT:-8001}}"
ENV_DIR="${ENV_DIR:-.venv-mlx}"
LLM_DIR="${LLM_DIR:-$(cd ../../.. && pwd)/moj-llm/my_folder}"
SYNTH="${SYNTH:-100}"
OLLAMA="${LLM_BASE_URL:-http://localhost:11434/v1}"
LLM_MODEL="${LLM_MODEL:-qwen3.5:4b}"
TAG="$(basename "$MODEL")"
LOG="results/basal_server_${TAG}.log"
mkdir -p results

say() { printf '\n\033[1m>> %s\033[0m\n' "$*"; }

# --- 0. Sprawdzenia -----------------------------------------------------------
[[ -x "$ENV_DIR/bin/basal-serve" ]] || { echo "Brak środowiska $ENV_DIR. Najpierw: ./scripts/run_on_mac.sh"; exit 1; }
[[ -f "$LLM_DIR/przetworz.py" ]] || { echo "Brak $LLM_DIR/przetworz.py. Sklonuj gałąź moj-llm (patrz README) albo ustaw LLM_DIR."; exit 1; }
curl -fs "${OLLAMA%/v1}/api/tags" >/dev/null || { echo "Ollama nie odpowiada na ${OLLAMA%/v1}. Uruchom: ollama serve"; exit 1; }
curl -fs "${OLLAMA%/v1}/api/tags" | grep -q "\"${LLM_MODEL}\"" || { echo "Brak modelu ${LLM_MODEL}. Uruchom: ollama pull ${LLM_MODEL}"; exit 1; }
# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"
python -c "import fastapi, openai, httpx" 2>/dev/null || { say "Doinstalowuję zależności warstwy porządkującej"; uv pip install -r "$LLM_DIR/requirements.txt"; }
uv pip install -q -e . >/dev/null

# --- 1. Nasze dane ---------------------------------------------------------------
say "Buduję nasze zbiory: realistyczne (63) i syntetyczne (${SYNTH})"
shipdec realistic >/dev/null
rm -rf data/synth_cmp data/synth_cmp_clean
shipdec generate -n "$SYNTH" --seed 7 --out-dir data/synth_cmp >/dev/null
rm -rf data/realistic_clean    # zbiór realistyczny zbudowany od nowa -> czysta wersja też

# --- 2. Oczyszczanie (Ollama) — przed Basalem, żeby oba modele nie zajmowały pamięci naraz ----
for D in realistic synth_cmp; do
  say "Oczyszczam data/${D} -> data/${D}_clean (${LLM_MODEL})"
  LLM_MODEL="$LLM_MODEL" shipdec clean --data-dir "data/${D}" --llm-dir "$LLM_DIR"
done
curl -fs "${OLLAMA%/v1}/api/generate" -d "{\"model\":\"${LLM_MODEL}\",\"keep_alive\":0}" >/dev/null || true  # zwolnij pamięć

# --- 3. Basal ---------------------------------------------------------------------
say "Startuję Basala (MLX). Log: ${LOG}"
basal-serve --model "$MODEL" --mode mlx --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
for i in $(seq 1 360); do
  curl -fs "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
  kill -0 $SERVER_PID 2>/dev/null || { echo "Serwer się zatrzymał:"; tail -30 "$LOG"; exit 1; }
  sleep 5
done

for D in realistic realistic_clean synth_cmp synth_cmp_clean; do
  say "Ewaluacja: data/${D}"
  shipdec evaluate --backend basal --url "http://127.0.0.1:${PORT}/v1/systemone" \
    --data-dir "data/${D}" --out "results/cmp_${D}.jsonl" | tail -8
done

# --- 4. Porównanie --------------------------------------------------------------------
for D in realistic synth_cmp; do
  say "PORÓWNANIE — ${D}: surowe vs oczyszczone"
  shipdec compare "results/cmp_${D}.jsonl" "results/cmp_${D}_clean.jsonl" | tee "results/cmp_${D}_porownanie.txt"
done
say "Gotowe. Porównania: results/cmp_*_porownanie.txt"
