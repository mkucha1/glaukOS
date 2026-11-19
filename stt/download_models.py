"""Run once with Internet. The API itself never downloads model weights."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["large-v3-turbo", "large-v3", "small"], default=os.getenv("MODEL_NAME", "large-v3"))
    parser.add_argument("--revision", default=None, help="Optional HF commit SHA for repeatable downloads")
    args = parser.parse_args()
    os.environ.pop("HF_HUB_OFFLINE", None)
    from huggingface_hub import HfApi, snapshot_download
    root = Path("/models")
    root.mkdir(parents=True, exist_ok=True)
    repos = {
        "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",
        "large-v3": "Systran/faster-whisper-large-v3",
        "small": "Systran/faster-whisper-small",
    }
    repo = repos[args.model]
    revision = HfApi().model_info(repo, revision=args.revision).sha
    print(f"Downloading {repo} at {revision}", flush=True)
    destination = root / f"whisper-{args.model}"
    snapshot_download(repo_id=repo, revision=revision, local_dir=str(destination),
                      allow_patterns=["*.json", "model.bin", "vocabulary.*"])
    for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
        if not (destination / name).is_file():
            raise RuntimeError(f"Missing model file: {name}")
    url = "https://raw.githubusercontent.com/Rikorose/DeepFilterNet/v0.5.6/models/DeepFilterNet3_onnx.tar.gz"
    expected = "c94d91f70911001c946e0fabb4aa9adc37045f45a03b56008cb0c8244cb63616"
    target = root / "DeepFilterNet3_onnx.tar.gz"
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        print("Downloading DeepFilterNet3 ONNX archive", flush=True)
        with urlopen(Request(url, headers={"User-Agent": "ship-stt-prototype"}), timeout=120) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError("DeepFilterNet3 checksum mismatch; refusing to save.")
        target.write_bytes(content)
    manifest = {"whisper_repo": repo, "whisper_revision": revision,
                "deepfilter_url": url, "deepfilter_sha256": expected}
    (root / f"manifest-{args.model}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Models ready. You can start the API without Internet.")


if __name__ == "__main__":
    main()
