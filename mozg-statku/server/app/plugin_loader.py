"""Ładuje funkcje modułów zespołu; `USE_STUBS=stt,refine,brain` wymusza zaślepki (plan B)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Plugins:
    transcribe: Callable
    refine: Callable
    structure: Callable
    check: Callable
    apply_clarification: Callable
    sources: dict


def load_plugins(force_stubs: set[str]) -> Plugins:
    from plugins import _stubs
    src = {}

    if "stt" in force_stubs:
        transcribe, src["stt"] = _stubs.stt_transcribe, "stub"
    else:
        from plugins import stt
        transcribe, src["stt"] = stt.transcribe, "plugins.stt"

    if "refine" in force_stubs:
        refine, src["refine"] = _stubs.refine_text, "stub"
    else:
        from plugins import refine as refine_mod
        refine, src["refine"] = refine_mod.refine, "plugins.refine"

    if "brain" in force_stubs:
        structure, check, apply_c = _stubs.brain_structure, _stubs.brain_check, _stubs.brain_apply_clarification
        src["brain"] = "stub"
    else:
        from plugins import brain
        structure, check, apply_c = brain.structure, brain.check, brain.apply_clarification
        src["brain"] = "plugins.brain"

    return Plugins(transcribe, refine, structure, check, apply_c, src)
