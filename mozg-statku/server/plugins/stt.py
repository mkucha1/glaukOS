"""MATEUSZ — mowa na tekst (odszumianie + transkrypcja).

KONTRAKT (nie zmieniaj sygnatury):
    transcribe(audio_path: str, lang_hint: str | None = None) -> dict
        audio_path  ścieżka do oryginalnego nagrania z telefonu (webm/opus z Androida,
                    mp4/aac z iPhone'a). Pomocnik: plugins.audio_utils.to_wav16k(path) -> path .wav 16 kHz mono
        lang_hint   język z profilu załoganta ("pl", "en", ...) albo None
    zwraca:
        {"text": "...", "lang": "pl", "duration_s": 3.2, "model": "large-v3-turbo",
         ... dowolne dodatkowe pola, np. "denoised": true, "segments": [...] }

Funkcja jest wołana w osobnym wątku (nie blokuje serwera) i nigdy dwa razy dla tego
samego nagrania — serwer pilnuje idempotencji. Wyjątek = serwer ponowi próbę, a potem
zapisze zdarzenie report.failed (widoczne dla oficera).
Model ładuj RAZ, leniwie (globalna zmienna), nie przy każdym wywołaniu.
"""
from __future__ import annotations

from plugins import _stubs

# --- przykład docelowej implementacji (odkomentuj i dopasuj) ---------------------------
# from faster_whisper import WhisperModel
# from plugins.audio_utils import to_wav16k
# _model = None
# MARITIME_PROMPT = "SFI, purifier, cooling water pump, mechanical seal, bar, ECR, auxiliary engine"
#
# def _get_model():
#     global _model
#     if _model is None:
#         _model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
#     return _model
#
# def transcribe(audio_path, lang_hint=None):
#     wav = to_wav16k(audio_path)          # + DeepFilterNet tutaj
#     segments, info = _get_model().transcribe(wav, language=lang_hint, initial_prompt=MARITIME_PROMPT, vad_filter=True)
#     text = " ".join(s.text.strip() for s in segments)
#     return {"text": text, "lang": info.language, "duration_s": info.duration, "model": "large-v3-turbo"}


def transcribe(audio_path: str, lang_hint: str | None = None) -> dict:
    # ====== MATEUSZ: zastąp tę linię swoim kodem ======
    return _stubs.stt_transcribe(audio_path, lang_hint)
