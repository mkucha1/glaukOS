#!/usr/bin/env bash
# Basal jako stały serwer dla serwera pokładowego (mozg-statku), na Macu z Apple Silicon (MLX).
# Działa na pierwszym planie; zatrzymanie: Ctrl+C. Środowisko tworzy scripts/run_on_mac.sh (pierwsze uruchomienie).
#
#   ./scripts/serve_mac.sh            # serwer mozg-statku uruchomiony w Pythonie (tryb A) -> 127.0.0.1:8001
#   DOCKER=1 ./scripts/serve_mac.sh   # serwer mozg-statku w Dockerze (tryb B) -> host.docker.internal:8001
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
[[ -n "${HF_TOKEN:-}" ]] || unset HF_TOKEN

MODEL="${MODEL:-${BASAL_MODEL:-Remek/basal-2.0-4.5B-MLX-8bit}}"
PORT="${PORT:-${BASAL_PORT:-8001}}"
ENV_DIR="${ENV_DIR:-.venv-mlx}"
[[ -x "$ENV_DIR/bin/basal-serve" ]] || { echo "Brak środowiska $ENV_DIR — uruchom raz ./scripts/run_on_mac.sh"; exit 1; }
# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"

if [[ "${DOCKER:-0}" == "1" ]]; then
  # Kontener woła host.docker.internal — Basal domyślnie przyjmuje tylko localhost, więc go dopuszczamy.
  exec basal-serve --model "$MODEL" --mode mlx --host 0.0.0.0 --port "$PORT" \
       --allowed-hosts "host.docker.internal,localhost,127.0.0.1"
else
  exec basal-serve --model "$MODEL" --mode mlx --host 127.0.0.1 --port "$PORT"
fi
