#!/usr/bin/env bash
# Basal na surowych wypowiedziach vs na tych samych wypowiedziach po oczyszczeniu warstwą LLM z gałęzi moj-llm.
#
# Co robi (domyślnie na 15 reprezentatywnych wypowiedziach z config/sample15.yaml):
#   1. buduje nasz zbiór: data/sample15 (albo realistyczne 63 / syntetyczne N — zmienna SETS)
#   2. czyści treść każdego zgłoszenia przez my_folder/przetworz.py (Ollama, qwen3.5:4b) -> data/<zbiór>_clean
#   3. startuje Basala (MLX) i ocenia OBA warianty: przed oczyszczeniem i po nim; zatrzymuje Basala
#   4. drukuje porównanie przed/po i zapisuje results/cmp_<zbiór>_przed_po.md (zgłoszenie po zgłoszeniu)
#
# Wymaga: folderu z gałęzią moj-llm (domyślnie ~/Documents/mari/moj-llm) i działającej Ollamy z modelem.
#   ollama serve            # jeśli nie działa jako aplikacja
#   ollama pull qwen3.5:4b
#
# Użycie (z backend/decision):
#   ./scripts/compare_cleaning_mac.sh                        # 15 wypowiedzi (kilka minut)
#   SETS="realistic synth_cmp" ./scripts/compare_cleaning_mac.sh   # 63 realistyczne + SYNTH syntetycznych
#   LLM_DIR=/inna/ścieżka/my_folder ./scripts/compare_cleaning_mac.sh
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
MODEL="${MODEL:-${BASAL_MODEL:-Remek/basal-2.0-4.5B-MLX-8bit}}"
PORT="${PORT:-${BASAL_PORT:-8001}}"
ENV_DIR="${ENV_DIR:-.venv-mlx}"
LLM_DIR="${LLM_DIR:-$(cd ../../.. && pwd)/moj-llm/my_folder}"
SYNTH="${SYNTH:-100}"
SETS="${SETS:-sample15}"
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
say "Buduję nasze zbiory: ${SETS}"
shipdec realistic >/dev/null
for D in $SETS; do rm -rf "data/${D}_clean"; done          # czysta wersja zawsze od nowa
[[ " $SETS " == *" sample15 "* ]] && shipdec sample
[[ " $SETS " == *" synth_cmp "* ]] && { rm -rf data/synth_cmp; shipdec generate -n "$SYNTH" --seed 7 --out-dir data/synth_cmp >/dev/null; }

# --- 2. Oczyszczanie (Ollama) — przed Basalem, żeby oba modele nie zajmowały pamięci naraz ----
for D in $SETS; do
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

for D in $SETS; do
  for V in "" "_clean"; do
    say "Ewaluacja: data/${D}${V}  ($([[ -z "$V" ]] && echo 'PRZED oczyszczeniem' || echo 'PO oczyszczeniu'))"
    shipdec evaluate --backend basal --url "http://127.0.0.1:${PORT}/v1/systemone" \
      --data-dir "data/${D}${V}" --out "results/cmp_${D}${V}.jsonl" | tail -8
  done
done

# --- 4. Porównanie --------------------------------------------------------------------
for D in $SETS; do
  say "PORÓWNANIE — ${D}: przed vs po oczyszczeniu"
  shipdec compare "results/cmp_${D}.jsonl" "results/cmp_${D}_clean.jsonl" --names przed po \
    --md "results/cmp_${D}_przed_po.md" --clean-dir "data/${D}_clean" | tee "results/cmp_${D}_porownanie.txt"
done
say "Gotowe. Tabela: results/cmp_*_porownanie.txt, zgłoszenie po zgłoszeniu: results/cmp_*_przed_po.md"
