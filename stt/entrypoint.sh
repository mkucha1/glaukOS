#!/bin/sh
set -eu
# Set this before importing CTranslate2. CUDA libraries live inside the container.
CUDA_LIBS="$(python -c 'import site; from pathlib import Path; p=Path(site.getsitepackages()[0])/"nvidia"; print(":".join(str(x) for x in sorted(p.glob("*/lib"))))')"
export LD_LIBRARY_PATH="${CUDA_LIBS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$@"
