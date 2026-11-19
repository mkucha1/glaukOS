#!/usr/bin/env bash
# Instalacja Basala na Linuksie/WSL z kartą NVIDIA (CUDA 12.8). Na Macu użyj scripts/run_on_mac.sh (MLX).
# Na podstawie https://github.com/rkinas/basal (v2.8.1).
set -euo pipefail
cd "$(dirname "$0")/.."
# Ustawienia z .env (jeśli jest); zmienne podane w linii poleceń mają pierwszeństwo.
if [[ -f .env ]]; then set -a; source .env; set +a; fi
[[ -n "${HF_TOKEN:-}" ]] || unset HF_TOKEN

ENV_DIR="${ENV_DIR:-.venv}"
BASAL_VERSION="${BASAL_VERSION:-v2.8.1}"
MODEL="${MODEL:-Remek/basal-2.0-4.5B}"   # na Linuksie/NVIDIA nie bierzemy BASAL_MODEL (domyślnie MLX)

[[ "$(uname)" != "Darwin" ]] || { echo "Na Macu: ./scripts/run_on_mac.sh"; exit 1; }
command -v uv >/dev/null || { echo "Brak uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }

uv venv --python 3.12 "$ENV_DIR"
# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"

# PyTorch z indeksu CUDA 12.8 (najnowszy torch z PyPI może wymagać nowszego sterownika)
uv pip install torch --index-url https://download.pytorch.org/whl/cu128
uv pip install "basal @ https://github.com/rkinas/basal/archive/refs/tags/${BASAL_VERSION}.tar.gz"
uv pip install -e ".[dev]" "huggingface_hub[cli]"

# Pobranie wag z góry, żeby pierwszy start serwera był szybszy
hf download "$MODEL"

echo
echo "Gotowe. Uruchom serwer:  ./scripts/serve_basal.sh"
