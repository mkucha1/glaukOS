"""Kontrakty danych między modułami zespołu (zamrożone po 0:30).

Pluginy (Mateusz / Maciej / Daniel) mogą zwracać zwykłe dict-y — serwer waliduje je tymi
modelami. Pola dodatkowe są dozwolone (extra="allow"), więc dodanie pola niczego nie psuje.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------ typy zdarzeń
EVENT_TYPES = {
    "report.recorded",
    "report.transcribed",
    "report.refined",       # Daniel: przerobiony (oczyszczony) raport przed strukturyzacją
    "report.structured",
    "report.clarification_requested",
    "report.clarified",
    "report.sensor_checked",
    "report.approved",
    "report.rejected",
    "report.failed",        # rozszerzenie: błąd modułu AI (z treścią błędu, pod audyt)
    "report.retry",         # rozszerzenie: ręczne ponowienie przetwarzania
    "task.assigned",
    "task.acknowledged",
    "task.escalated",
    "task.closed",
    "sync.sent",            # lokalne — nie idzie na ląd
    "sync.link_changed",    # lokalne — nie idzie na ląd
}


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


# ------------------------------------------------------------------ Mateusz: mowa -> tekst
class TranscriptResult(_Open):
    text: str
    lang: str = "und"                     # ISO 639-1, np. "pl"
    duration_s: Optional[float] = None
    model: Optional[str] = None


# ------------------------------------------------------------------ Maciej: formularz + decyzja
class ReportForm(_Open):
    equipment: Optional[str] = None
    sfi_code: Optional[str] = None
    parameter: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    defect: Optional[str] = None
    priority: int = Field(default=3, ge=1, le=5)
    location: Optional[str] = None
    action_taken: Optional[str] = None
    text_en: str = ""
    lang_original: str = "und"
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class SensorCheck(_Open):
    tag: str
    parameter: Optional[str] = None
    reported: Optional[float] = None
    measured: Optional[float] = None
    unit: Optional[str] = None
    tolerance: Optional[float] = None
    ok: Optional[bool] = None          # None = brak danych z czujnika
    age_s: Optional[float] = None


class Clarification(_Open):
    question: str                       # w języku załoganta (czytane przez speechSynthesis)
    lang: str = "en"
    question_en: Optional[str] = None   # do rejestru / dla oficera
    field: Optional[str] = None


class Decision(_Open):
    priority: int = Field(default=3, ge=1, le=5)
    route_role: str = "chief_engineer"  # kto zatwierdza -> temat role/{route_role}/approve
    dept: str = "engine"                # "engine" -> temat ship/{id}/eng/new
    checks: list[SensorCheck] = Field(default_factory=list)
    clarification: Optional[Clarification] = None
    notes: list[str] = Field(default_factory=list)
    # None = decyduje próg pewności (form.confidence vs AUTO_APPROVE_CONFIDENCE);
    # True = zawsze do oficera, False = wolno zatwierdzić automatycznie
    needs_officer: Optional[bool] = None
    assignee: Optional[str] = None      # komu przydzielić zadanie przy automatycznym zatwierdzeniu


# ------------------------------------------------------------------ Daniel: przerobienie raportu
class RefineResult(_Open):
    text: str                           # oczyszczony tekst raportu (wejście dla brain.structure)
    lang: Optional[str] = None          # None = bez zmiany języka


# ------------------------------------------------------------------ API (wejście)
class ApproveIn(BaseModel):
    event_id: Optional[str] = None
    officer_id: str
    decision: Literal["approve", "reject"] = "approve"
    assignee: Optional[str] = None
    note: Optional[str] = None
    form_patch: dict[str, Any] = Field(default_factory=dict)  # poprawki oficera do formularza


class TaskActionIn(BaseModel):
    event_id: Optional[str] = None
    crew_id: str
    note: Optional[str] = None


class TextReportIn(BaseModel):
    report_id: str
    crew_id: str
    text: str
    lang: Optional[str] = None
    device: Optional[str] = None
    recorded_at: Optional[str] = None
    event_id: Optional[str] = None


class LinkIn(BaseModel):
    up: bool
    actor: Optional[str] = None
