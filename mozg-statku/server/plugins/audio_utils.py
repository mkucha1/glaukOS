"""Pomocnicze funkcje audio dla modułu STT (ffmpeg jest w obrazie Dockera)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def to_wav16k(audio_path: str) -> str:
    """Konwertuje dowolne nagranie z przeglądarki (webm/opus, mp4/aac, ogg) do WAV 16 kHz mono.
    Wynik jest cache'owany obok oryginału: <plik>.16k.wav."""
    src = Path(audio_path)
    dst = src.with_name(src.name + ".16k.wav")
    if not dst.exists():
        tmp = dst.with_name(dst.name + ".tmp.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(tmp)],
                       check=True)
        tmp.replace(dst)
    return str(dst)
