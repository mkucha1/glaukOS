"""Local audio pipeline. No database, translation or automatic report approval."""
import logging
import os
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


class AudioError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Settings:
    model_path: str = os.getenv("MODEL_PATH", "/models/whisper-large-v3")
    model_name: str = os.getenv("MODEL_NAME", "large-v3")
    device: str = os.getenv("DEVICE", "cuda")
    compute_type: str = os.getenv("COMPUTE_TYPE", "float16")
    denoise: bool = os.getenv("DENOISE", "true").lower() == "true"
    df_model_path: str = os.getenv("DF_MODEL_PATH", "/models/DeepFilterNet3_onnx.tar.gz")
    df_binary: str = os.getenv("DF_BINARY", "deep-filter")
    ffmpeg: str = os.getenv("FFMPEG", "ffmpeg")
    max_seconds: int = int(os.getenv("MAX_AUDIO_SECONDS", "120"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def run_program(args: list[str], timeout: int, label: str) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise AudioError(f"Brak programu: {label}. Sprawdz obraz kontenera.", 503) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioError(f"Przekroczono czas etapu: {label}.", 504) from exc
    except subprocess.CalledProcessError as exc:
        log.error("%s failed: %s", label, exc.stderr.decode(errors="replace")[-2000:])
        code = 422 if label == "FFmpeg" else 503
        raise AudioError(f"Blad etapu {label}. Sprawdz format audio lub logi serwisu.", code) from exc


def prepare_wav(source: Path, target: Path, cfg: Settings) -> dict:
    run_program([
        cfg.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:a:0",
        "-vn", "-t", str(cfg.max_seconds + 1), "-ac", "1", "-ar", "48000",
        "-c:a", "pcm_s16le", str(target),
    ], 45, "FFmpeg")
    with wave.open(str(target), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32) / 32768
    if duration > cfg.max_seconds:
        raise AudioError(f"Nagranie przekracza {cfg.max_seconds} sekund.")
    if duration < 0.15:
        raise AudioError("Nagranie jest za krotkie; nagraj ponownie.")
    rms = float(np.sqrt(np.mean(samples ** 2)))
    return {
        "audio_seconds": round(duration, 3),
        "rms_dbfs": round(20 * np.log10(max(rms, 1e-12)), 2),
        "near_full_scale_fraction": round(float(np.mean(np.abs(samples) >= 0.995)), 6),
        "digital_silence": rms < 1e-6,
    }


def denoise_wav(source: Path, out_dir: Path, cfg: Settings) -> Path:
    if not Path(cfg.df_model_path).is_file():
        raise AudioError("Brak modelu DeepFilterNet3. Uruchom download_models.py.", 503)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Pad the end before -D: the v0.5.6 CLI removes its algorithmic delay
    # but does not append samples to flush the last word itself.
    padded = out_dir.parent / "padded.wav"
    run_program([
        cfg.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-af", "apad=pad_dur=0.1", "-c:a", "pcm_s16le", str(padded),
    ], 15, "FFmpeg")
    run_program([
        cfg.df_binary, "-m", cfg.df_model_path, "-D", "-o", str(out_dir), str(padded),
    ], 180, "DeepFilterNet3")
    output = out_dir / padded.name
    if not output.is_file() or output.stat().st_size <= 44:
        raise AudioError("DeepFilterNet nie utworzyl pliku audio.", 503)
    return output


class SpeechPipeline:
    def __init__(self, cfg: Settings, model=None):
        self.cfg = cfg
        if model is None:
            if cfg.denoise and not Path(cfg.df_model_path).is_file():
                raise RuntimeError("Missing DeepFilterNet3 model. Run download_models.py first.")
            if not (Path(cfg.model_path) / "model.bin").is_file():
                raise RuntimeError("Brak modelu Whisper. Najpierw uruchom download_models.py.")
            from faster_whisper import WhisperModel
            model = WhisperModel(
                cfg.model_path, device=cfg.device, compute_type=cfg.compute_type,
                local_files_only=True, cpu_threads=4, num_workers=1,
            )
        self.model = model

    def process(self, source: Path, work: Path) -> str:
        wav = work / "input_48k.wav"
        diagnostics = prepare_wav(source, wav, self.cfg)
        if diagnostics["digital_silence"]:
            return ""
        selected = denoise_wav(wav, work / "denoised", self.cfg) if self.cfg.denoise else wav
        generated, _ = self.model.transcribe(
            str(selected), task="transcribe", language=None,
            beam_size=5, temperature=0, condition_on_previous_text=False,
            vad_filter=True, vad_parameters={"min_speech_duration_ms": 0},
            word_timestamps=False,
        )
        return " ".join(segment.text.strip() for segment in generated).strip()


