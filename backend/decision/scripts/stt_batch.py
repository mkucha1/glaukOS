"""Etap 1 potoku głosowego: nagrania -> tekst, kodem STT z gałęzi `stt` (stt/app/pipeline.py).

Uruchamiany w osobnym środowisku (.venv-stt), bo faster-whisper ma inne zależności niż Basal/MLX.
Kod STT zespołu jest używany bez zmian (SpeechPipeline.process: ffmpeg -> [DeepFilterNet] -> Whisper);
podajemy mu tylko ustawienia dla Maca: CPU + int8 zamiast CUDA + float16 (na Macu nie ma CUDA).

    python scripts/stt_batch.py --stt-dir ../../../stt/stt --models-dir ../../../models \
        --out results/voice/stt.jsonl ../../../data/*.wav ../../../data/*.mp3

Wynik: jedna linia JSON na nagranie: {audio, text, stt_s, model, device, denoise}.
Model Whisper pobiera się raz z Hugging Face (te same repozytoria co stt/download_models.py).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

REPOS = {  # jak w stt/download_models.py
    "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",
    "large-v3": "Systran/faster-whisper-large-v3",
    "small": "Systran/faster-whisper-small",
}


def ensure_model(models_dir: Path, name: str) -> Path:
    target = models_dir / f"whisper-{name}"
    if not (target / "model.bin").is_file():
        from huggingface_hub import snapshot_download
        print(f"Pobieram {REPOS[name]} -> {target} (jednorazowo)", file=sys.stderr, flush=True)
        snapshot_download(repo_id=REPOS[name], local_dir=str(target),
                          allow_patterns=["*.json", "model.bin", "vocabulary.*"])
    return target


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", nargs="+")
    p.add_argument("--stt-dir", required=True, help="folder `stt` z gałęzi stt (zawiera app/pipeline.py)")
    p.add_argument("--models-dir", required=True)
    p.add_argument("--model", default="large-v3", choices=sorted(REPOS))
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute-type", default="int8")
    p.add_argument("--denoise", action="store_true", help="DeepFilterNet3 (wymaga programu deep-filter i modelu)")
    p.add_argument("--out", required=True)
    a = p.parse_args()

    stt_dir = Path(a.stt_dir).resolve()
    if not (stt_dir / "app" / "pipeline.py").is_file():
        print(f"Brak {stt_dir}/app/pipeline.py — sklonuj gałąź stt", file=sys.stderr)
        return 1
    sys.path.insert(0, str(stt_dir))
    from app.pipeline import AudioError, Settings, SpeechPipeline  # kod zespołu, bez zmian

    models = Path(a.models_dir).resolve()
    models.mkdir(parents=True, exist_ok=True)
    cfg = Settings(model_path=str(ensure_model(models, a.model)), model_name=a.model, device=a.device,
                   compute_type=a.compute_type, denoise=a.denoise,
                   df_model_path=str(models / "DeepFilterNet3_onnx.tar.gz"))
    t0 = time.perf_counter()
    pipe = SpeechPipeline(cfg)
    print(f"Whisper {a.model} ({a.device}/{a.compute_type}) załadowany w {time.perf_counter() - t0:.0f} s",
          file=sys.stderr, flush=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for audio in a.audio:
            t0 = time.perf_counter()
            try:
                with TemporaryDirectory(prefix="glaukos-stt-") as work:
                    text, error = pipe.process(Path(audio), Path(work)), None
            except AudioError as e:
                text, error = "", str(e)
            row = {"audio": str(Path(audio).resolve()), "text": text, "error": error,
                   "stt_s": round(time.perf_counter() - t0, 1), "model": a.model,
                   "device": f"{a.device}/{a.compute_type}", "denoise": a.denoise}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[STT] {Path(audio).name}  {row['stt_s']} s  {error or text}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
