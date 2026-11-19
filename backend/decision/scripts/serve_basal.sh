#!/usr/bin/env bash
# Start serwera Basala na Linuksie z kartą NVIDIA (na Macu użyj scripts/run_on_mac.sh).
#   MODE=fast-nocompile  — start w kilka sekund (domyślnie, wygodne przy rozwoju)
#   MODE=fast            — najszybsze odpowiedzi, pierwszy start kompiluje model kilka minut
#   MODE=fp8 MODEL=Remek/basal-2.0-4.5B-FP8  — karty Hopper/Blackwell (sm89+)
set -euo pipefail
cd "$(dirname "$0")/.."
# Ustawienia z .env (jeśli jest); zmienne podane w linii poleceń mają pierwszeństwo.
if [[ -f .env ]]; then set -a; source .env; set +a; fi
[[ -n "${HF_TOKEN:-}" ]] || unset HF_TOKEN

ENV_DIR="${ENV_DIR:-.venv}"
MODEL="${MODEL:-Remek/basal-2.0-4.5B}"   # na Linuksie/NVIDIA nie bierzemy BASAL_MODEL (domyślnie MLX)
MODE="${MODE:-fast-nocompile}"
PORT="${PORT:-${BASAL_PORT:-8000}}"

# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"
# --template-prefix off: zalecane przez autora dla modelu 4.5B (bf16 i FP8)
EXTRA=()
[[ "$MODEL" == *4.5B* ]] && EXTRA=(--template-prefix off)
exec basal-serve --model "$MODEL" --mode "$MODE" "${EXTRA[@]}" --port "$PORT"
