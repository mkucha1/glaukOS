"""
Warstwa porządkująca tekst: surowa wypowiedź z STT -> zgłoszenie JSON dla modelu decyzyjnego.

[Moduł STT] --POST /parse--> [ta aplikacja (lokalny LLM)] --zgłoszenie JSON--> [Model decyzyjny (Basal)]

Aplikacja NIE podejmuje decyzji (dział, pilność, raport DPA, osoba) - to robi model decyzyjny
(github/backend/decision). Tutaj tylko porządkujemy wypowiedź: usuwamy wypełniacze i autokorekty,
zamieniamy liczby na cyfry i zostawiamy krótki, prosty tekst z tymi samymi informacjami, co w nagraniu.
Ten tekst trafia do pola `tresc`, które jako JEDYNE czyta model decyzyjny. Nadaje się też do odczytu przez TTS.

Format wyjścia = format zgłoszenia z github/backend/decision (schema_version 0.1) + pola tej warstwy.

Uruchomienie:
    python app.py                     # port 8010 (8000 zajmuje serwer Basala)
    LLM_MOCK=1 python app.py          # bez LLM (proste czyszczenie) - do testów integracji
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from openai import APIConnectionError, APITimeoutError, OpenAI
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

# ==========================================
# KONFIGURACJA (zmienne środowiskowe)
# ==========================================
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5:4b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "local")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "2"))  # ponowienie przy błędnym JSON
# "none" wyłącza tryb "thinking" (Qwen3 itp.): ~2 s zamiast ~30 s na zgłoszenie.
# Ustaw pusty string, jeśli Twój serwer LLM nie obsługuje tego parametru.
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "none")
LLM_MOCK = os.getenv("LLM_MOCK", "0").lower() in ("1", "true", "yes")

# Język tekstu w `tresc`: "auto" = język mówiącego (jak streszczenia wzorcowe w projekcie decyzyjnym),
# albo wymuszony kod ISO, np. "en" lub "pl".
SUMMARY_LANGUAGE = os.getenv("SUMMARY_LANGUAGE", "auto").strip().lower()
SHIP_NAME = os.getenv("SHIP_NAME", "").strip() or None  # domyślne `statek`, jeśli STT go nie poda

# Opcjonalnie: automatyczne przekazanie zgłoszenia do modelu decyzyjnego (POST JSON).
DECISION_URL = os.getenv("DECISION_URL", "").strip()
DECISION_TIMEOUT = float(os.getenv("DECISION_TIMEOUT", "10"))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8010"))

REPORT_SCHEMA_VERSION = "0.1"  # = SCHEMA_VERSION w github/backend/decision/src/shipdec/generate.py
PARSER_VERSION = "2.0"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("stt-parser")

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=LLM_TIMEOUT, max_retries=1)

app = FastAPI(title="STT -> zgłoszenie (warstwa porządkująca tekst)", version=PARSER_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UNCLEAR_TEXT = {
    "pl": "Brak konkretnej treści — dopytać zgłaszającego, czego dotyczy zgłoszenie.",
    "en": "No specific content — ask the reporter what the report is about.",
}


# ==========================================
# WEJŚCIE (z modułu STT / aplikacji)
# ==========================================

class STTInput(BaseModel):
    """Wypowiedź z STT. Wymagany jest tylko tekst. Można też wysłać od razu całe zgłoszenie
    w formacie projektu decyzyjnego (z polem `tresc`) - metadane przejdą bez zmian."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    text: str = Field(
        ...,
        min_length=2,
        max_length=5000,
        validation_alias=AliasChoices("text", "tresc", "transcript", "transcription"),
        description="Surowa wypowiedź z STT (akceptowane też: tresc, transcript, transcription)",
    )
    stt_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        validation_alias=AliasChoices("stt_confidence", "confidence", "stt_pewnosc"),
        description="Opcjonalna pewność z STT (0.0-1.0)",
    )
    language: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("language", "jezyk"),
        description="Podpowiedź języka z STT, np. 'pl'",
    )
    # --- metadane zgłoszenia (przechodzą bez zmian; brakujące uzupełniamy) ---
    id: Optional[str] = Field(default=None, validation_alias=AliasChoices("id", "request_id"))
    statek: Optional[str] = None
    czas_utc: Optional[str] = None
    wachta: Optional[str] = None
    zglaszajacy: Optional[dict[str, Any]] = None
    lokalizacja: Optional[str] = None
    kanal: Optional[str] = None
    urzadzenie: Optional[str] = Field(default=None, validation_alias=AliasChoices("urzadzenie", "source_id", "device"))
    nagranie_s: Optional[float] = Field(default=None, validation_alias=AliasChoices("nagranie_s", "duration_s"))

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("text is empty after stripping whitespace")
        return v


# ==========================================
# WYJŚCIE = zgłoszenie dla modelu decyzyjnego
# ==========================================

class Porzadkowanie(BaseModel):
    """Informacje o pracy tej warstwy (model decyzyjny ich nie potrzebuje)."""
    wersja: str = PARSER_VERSION
    model: str
    czas_ms: int
    proby: int
    stt_pewnosc: Optional[float] = None


class Zgloszenie(BaseModel):
    """Zgłoszenie w formacie github/backend/decision (schema_version 0.1).
    Model decyzyjny czyta WYŁĄCZNIE `tresc`. Pola po `tresc` dodaje ta warstwa."""

    schema_version: str = REPORT_SCHEMA_VERSION
    id: str
    statek: Optional[str] = None
    czas_utc: str
    wachta: str
    zglaszajacy: Optional[dict[str, Any]] = None
    lokalizacja: Optional[str] = None
    kanal: str = "glos"
    urzadzenie: Optional[str] = None
    jezyk: str
    nagranie_s: Optional[float] = None
    tresc: str = Field(..., description="Uporządkowana wypowiedź: prosty tekst, te same informacje co w nagraniu")
    tresc_surowa: str = Field(..., description="Oryginalny tekst z STT")
    niejednoznaczne: bool = Field(..., description="true = brak konkretnej treści, aplikacja powinna dopytać")
    porzadkowanie: Porzadkowanie


class ErrorBody(BaseModel):
    error: str
    message: str
    id: Optional[str] = None


# ==========================================
# LICZBY MÓWIONE -> CYFRY (PL/EN), zanim tekst trafi do LLM
# ==========================================
# Mały model myli np. "trzysta osiemdziesiąt" (380 -> 280). Zamieniamy tylko jednoznaczne, poprawnie
# zbudowane liczebniki. Nietypowe ciągi ("cztery sześć", "three eighty") zostają słowami - oceni je LLM.

def _num_words() -> dict[str, tuple[int, int]]:
    """słowo -> (wartość, rząd): 0=jedności, 1=nastki/dziesiątki, 2=setki"""
    w: dict[str, tuple[int, int]] = {}
    pl_units = ["zero", "jeden|jedna|jedno|jednego|jednej", "dwa|dwie|dwóch|dwoch|dwu|dwoma",
                "trzy|trzech|trzema", "cztery|czterech|czterema", "pięć|piec|pięciu|pieciu",
                "sześć|szesc|sześciu|szesciu", "siedem|siedmiu", "osiem|ośmiu|osmiu",
                "dziewięć|dziewiec|dziewięciu|dziewieciu"]
    pl_teens = ["dziesięć|dziesiec|dziesięciu|dziesieciu", "jedenaście|jedenascie|jedenastu",
                "dwanaście|dwanascie|dwunastu", "trzynaście|trzynascie|trzynastu",
                "czternaście|czternascie|czternastu", "piętnaście|pietnascie|piętnastu|pietnastu",
                "szesnaście|szesnascie|szesnastu", "siedemnaście|siedemnascie|siedemnastu",
                "osiemnaście|osiemnascie|osiemnastu", "dziewiętnaście|dziewietnascie|dziewiętnastu|dziewietnastu"]
    pl_tens = ["dwadzieścia|dwadziescia|dwudziestu", "trzydzieści|trzydziesci|trzydziestu",
               "czterdzieści|czterdziesci|czterdziestu", "pięćdziesiąt|piecdziesiat|pięćdziesięciu",
               "sześćdziesiąt|szescdziesiat|sześćdziesięciu", "siedemdziesiąt|siedemdziesiat|siedemdziesięciu",
               "osiemdziesiąt|osiemdziesiat|osiemdziesięciu", "dziewięćdziesiąt|dziewiecdziesiat|dziewięćdziesięciu"]
    pl_hundreds = ["sto|stu", "dwieście|dwiescie|dwustu", "trzysta|trzystu", "czterysta|czterystu",
                   "pięćset|piecset|pięciuset", "sześćset|szescset|sześciuset", "siedemset|siedmiuset",
                   "osiemset|ośmiuset", "dziewięćset|dziewiecset|dziewięciuset"]
    en_units = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    en_teens = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                "eighteen", "nineteen"]
    en_tens = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    for i, forms in enumerate(pl_units):
        w.update({f: (i, 0) for f in forms.split("|")})
    for i, forms in enumerate(pl_teens):
        w.update({f: (10 + i, 1) for f in forms.split("|")})
    for i, forms in enumerate(pl_tens):
        w.update({f: (20 + 10 * i, 1) for f in forms.split("|")})
    for i, forms in enumerate(pl_hundreds):
        w.update({f: (100 * (i + 1), 2) for f in forms.split("|")})
    w.update({f: (i, 0) for i, f in enumerate(en_units)})
    w.update({f: (10 + i, 1) for i, f in enumerate(en_teens)})
    w.update({f: (20 + 10 * i, 1) for i, f in enumerate(en_tens)})
    return w


_NUM_WORDS = _num_words()
_THOUSAND = {"tysiąc", "tysiac", "tysiące", "tysiace", "tysięcy", "tysiecy", "thousand"}
_JOINERS = {"hundred", "and"} | _THOUSAND
_TOKEN = re.compile(r"\w+|\W+")


def _parse_number(words: list[str]) -> Optional[int]:
    """Poprawnie zbudowany liczebnik -> int; nietypowy ciąg -> None."""
    total, current, last_rank = 0, 0, 3
    for k, w in enumerate(words):
        if w in _NUM_WORDS:
            val, rank = _NUM_WORDS[w]
            if rank >= last_rank:
                return None
            current += val
            last_rank = 0 if rank == 1 and val < 20 else rank  # po nastce nie ma jedności
        elif w == "hundred" and 0 < current < 10:
            current *= 100
            last_rank = 2
        elif w == "and" and last_rank == 2 and k + 1 < len(words):
            continue
        elif w in _THOUSAND:
            total += (current or 1) * 1000
            current, last_rank = 0, 3
        else:
            return None
    return total + current


def normalize_numbers(text: str) -> str:
    """'trzysta osiemdziesiąt wolt' -> '380 wolt', 'dwa przecinek pięć' -> '2.5', 'trzy i pół' -> '3.5'."""
    tokens = _TOKEN.findall(text)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i].lower() not in _NUM_WORDS and tokens[i].lower() not in _THOUSAND:
            out.append(tokens[i])
            i += 1
            continue
        # maksymalny ciąg słów liczbowych rozdzielonych samymi spacjami
        j = i
        while j + 2 < len(tokens) and tokens[j + 1].isspace() and tokens[j + 2].lower() in (_NUM_WORDS.keys() | _JOINERS):
            j += 2
        words = [tokens[k].lower() for k in range(i, j + 1, 2)]
        while words and words[-1] == "and":  # "five and" na końcu ciągu to nie część liczby
            words.pop()
            j -= 2
        value = _parse_number(words)
        # Pojedyncze małe liczebniki ("dwie beczki", "numer dwa") zostają słowami - model radzi sobie z nimi,
        # a cyfra potrafi zmienić sens ("olej do sprężarki 2 beczki" -> "sprężarka nr 2").
        simple = value is not None and len(words) == 1 and value <= 10
        if value is None or (simple and not re.match(r"\s+(?:przecinek|point|i pół|i pol|and a half)\b",
                                                     "".join(tokens[j + 1:j + 7]).lower())):
            out.extend(tokens[i:j + 1])  # nietypowy ciąg zostawiamy bez zmian
            i = j + 1
            continue
        number: float = value
        end = j + 1
        # część dziesiętna: "przecinek pięć" / "point five" / "i pół" / "and a half"
        nxt = [t.lower() for t in tokens[end:end + 6]]
        if len(nxt) >= 4 and nxt[0].isspace() and nxt[1] in ("przecinek", "point") and nxt[3] in _NUM_WORDS \
                and _NUM_WORDS[nxt[3]][1] == 0:
            number = float(f"{value}.{_NUM_WORDS[nxt[3]][0]}")
            end += 4
        elif len(nxt) >= 4 and nxt[0].isspace() and nxt[1] == "i" and nxt[3] in ("pół", "pol"):
            number += 0.5
            end += 4
        elif len(nxt) >= 6 and nxt[1] == "and" and nxt[3] == "a" and nxt[5] == "half":
            number += 0.5
            end += 6
        out.append(f"{number:g}")
        i = end
    return "".join(out)


# ==========================================
# PROMPT
# ==========================================

SYSTEM_PROMPT = """
You clean up voice reports from a ship's crew (deck, engine room, galley) after speech-to-text.
The output text is read by the ship's decision system and may be read aloud by text-to-speech.

Write `tresc`: the same information as the speaker gave, as short, plain, correct sentences
in natural, grammatical Polish or English.
- Keep EVERY fact: equipment and its number, side/location, readings with units, what was ALREADY DONE
  (e.g. wiped up, put a drip tray, switched over, informed someone), whether it is getting worse,
  what is needed or must be ordered (with quantities), deadlines, who was informed, requests for a decision,
  and the speaker's own words about urgency ("nic pilnego", "to pilne") or uncertainty ("ok.", "about").
- If the speaker says what kind of message it is, start with it: "Przekazanie wachty:", "Watch handover:",
  "Obchód maszynowni:", "Do zamówienia:", "Order list:".
- Keep each number with the item it was said about. Never move a number to another item.
- Keep the mode of every statement: DONE ("wytarłem" -> "wytarto"), TO BE DONE ("trzeba zgłosić" ->
  "do zgłoszenia", "need to report" -> "to be reported"), or a REQUEST/INSTRUCTION ("chief cook said to report"
  -> "Chief cook asked for it to be reported"). Never turn something that is to be done into something done.
  First person future ("sprawdzę", "wymienię", "I will check") is TO BE DONE ("do sprawdzenia", "to be checked").
- Always keep statements that nobody was hurt or nothing happened ("nikomu nic", "nobody injured").
- In Polish "ten", "ta", "to" are pronouns ("this"), never the number 10.
- Keep who did what to whom. Never change the subject or object ("lina odbiła, marynarz odskoczył" means the
  rope snapped back and the sailor jumped away - it did NOT hit the sailor).
- People: keep exactly the person the speaker named. "chief"/"chiefa"/"stary mechanik" = starszy mechanik
  (Chief Engineer), "kapitan"/"master"/"stary" = kapitan (Master), "bosman"/"bosun" = bosman.
  Never replace one person with another.
- Keep the speaker's technical terms if unsure how to rephrase them (e.g. "skuwanie rdzy", "top coat", "kingston").
- Copy names of equipment exactly; similar-looking words are different equipment:
  "zęzowa/zęzowy/zęza" (bilge) is NOT "zębowa/zębowy" (gear); "balastowa" (ballast) is NOT "bazowa".
- Remove filler words, hesitations, greetings, swearing, repetitions and false starts
  ("yyy", "eee", "no to tak", "kurde", "znaczy", "Sir", "ah", "how you call").
- Self-corrections: keep only the corrected version ("dwójka, znaczy dwa lewy" -> "2L").
  If the speaker is unsure between values, keep the uncertainty ("ok. 4,5 bar").
- Numbers as digits with units (4,5 bar in Polish, 4.5 bar in English, 128 m³, 85°C, 12,5 w., 04:00).
  A course or heading spoken digit by digit ("dwa-trzy-pięć", "two three five") is one number: 235°.
- Do NOT add anything that was not said: no causes, no assessments, no priority, no department,
  no person to assign, no recommendations, no extra details about other equipment.
- Words the STT could not recognise are marked "*": skip them, keep the rest, do not guess.
- Plain text only: 1-3 sentences, no lists, no line breaks, no markdown, no headings.

`niejednoznaczne`: true ONLY if the speech contains no concrete information at all (no equipment, place,
event, task or reading), e.g. "yyy nic, wszystko dobrze, znaczy normalnie". Then `tresc` may be empty.
If anything concrete is left (even with "*" gaps, e.g. "* the pilot ladder checked * okay"), it is false.

`jezyk`: 2-letter ISO code of the speaker's language ("pl", "en", ...).

Examples:
Speech (pl): "eee no więc sprężarka powietrza numer jeden, znaczy dwójka, znowu wywaliła na wysokiej temperaturze, 85 stopni, przełączyłem na jedynkę, trzeba by zobaczyć chłodnicę"
JSON: {"jezyk":"pl","tresc":"Sprężarka powietrza nr 2 ponownie wyłączyła się na wysokiej temperaturze (85°C). Przełączono na sprężarkę nr 1. Chłodnica do sprawdzenia.","niejednoznaczne":false}
Speech (pl): "kurczę w pentrze cieknie zawór pod zlewem, ten zimnej wody, zakręciłem go i podłożyłem szmatę, ale coraz bardziej, i jeszcze potrzebne trzy żarówki do mesy"
JSON: {"jezyk":"pl","tresc":"W pentrze cieknie zawór zimnej wody pod zlewem, przeciek narasta. Zawór zakręcono i podłożono szmatę. Potrzebne trzy żarówki do mesy.","niejednoznaczne":false}
Speech (pl): "no pompa zęzowa jedynka znowu nie łapie ssania, odpowietrzyłem, zęzy pod silnikiem do połowy"
JSON: {"jezyk":"pl","tresc":"Pompa zęzowa nr 1 ponownie nie łapie ssania; odpowietrzono ją. Zęzy pod silnikiem wypełnione do połowy.","niejednoznaczne":false}
Speech (en): "Ah sir, the galley oven number 2, ah, the door not closing good, we still using but heat going out, maybe need new gasket"
JSON: {"jezyk":"en","tresc":"Galley oven No. 2: door does not close properly and heat escapes; still in use. A new door gasket may be needed.","niejednoznaczne":false}
""".strip()

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "jezyk": {"type": "string"},
        "tresc": {"type": "string"},
        "niejednoznaczne": {"type": "boolean"},
    },
    "required": ["jezyk", "tresc", "niejednoznaczne"],
    "additionalProperties": False,
}
LLM_RESPONSE_FORMAT = {"type": "json_schema", "json_schema": {"name": "Porzadkowanie", "schema": LLM_SCHEMA}}


# ==========================================
# LLM
# ==========================================

class LLMUnavailable(Exception):
    pass


class LLMBadOutput(Exception):
    pass


def clean_json_response(raw: str) -> str:
    """Usuwa bloki <think>...</think>, znaczniki ```json i tekst przed/po obiekcie JSON."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return cleaned


def _norm_lang(v: Any, fallback: Optional[str]) -> str:
    v = str(v or "").strip().lower()[:2]
    if re.fullmatch(r"[a-z]{2}", v):
        return v
    return (fallback or "und").lower()[:2]


def _plain_text(s: str) -> str:
    """Jedna linia zwykłego tekstu (TTS): bez markdownu, punktorów i podwójnych spacji."""
    s = re.sub(r"[*_#`]+", "", s)
    s = re.sub(r"(?m)^\s*(?:[-•·]|\d+[.)])\s+", "", s)
    s = " ".join(s.split())
    if s and s[-1] not in ".!?":
        s += "."
    return s


def _parse_llm(raw: str) -> dict:
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError("expected a JSON object")
    tresc = _plain_text(str(d.get("tresc") or ""))
    unclear = bool(d.get("niejednoznaczne"))
    if not unclear and len(tresc) < 3:
        raise ValueError("`tresc` is empty but `niejednoznaczne` is false")
    return {"jezyk": d.get("jezyk"), "tresc": tresc, "niejednoznaczne": unclear}


def chat_json(messages: list[dict]) -> tuple[dict, int]:
    """Woła LLM o JSON; przy niepoprawnym wyniku ponawia z opisem błędu. Zwraca (wynik, liczba prób)."""
    extra = {"reasoning_effort": LLM_REASONING_EFFORT} if LLM_REASONING_EFFORT else {}
    last_err: Exception | None = None
    for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
        try:
            completion = client.chat.completions.create(
                model=LLM_MODEL, temperature=0.0, messages=messages,
                response_format=LLM_RESPONSE_FORMAT, **extra,
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMUnavailable(f"LLM server unreachable at {LLM_BASE_URL}: {exc}") from exc
        raw = completion.choices[0].message.content or ""
        try:
            return _parse_llm(clean_json_response(raw)), attempt
        except ValueError as exc:  # json.JSONDecodeError też jest ValueError
            last_err = exc
            log.warning("attempt %d: invalid LLM output (%s). Raw: %.300s", attempt, exc, raw)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Your JSON was invalid: {exc}. Return the corrected JSON only."},
            ]
    raise LLMBadOutput(f"LLM returned invalid JSON after {LLM_MAX_ATTEMPTS} attempts: {last_err}")


def call_llm(stt: STTInput) -> tuple[dict, int]:
    lang_hint = stt.language or "unknown"
    # język wyniku: wymuszony z konfiguracji, albo język mówiącego podany przez STT/aplikację
    target_lang = SUMMARY_LANGUAGE if SUMMARY_LANGUAGE != "auto" else (stt.language or "").lower()[:2] or None
    if target_lang:
        target = f"Write `tresc` in this language: {target_lang} (translate if needed)."
    else:
        target = "Write `tresc` in the same language as the speaker."
    user_msg = (f"{target}\nLanguage hint from STT: {lang_hint}\n"
                f'Speech:\n"""{normalize_numbers(stt.text)}"""')
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_msg}]
    out, attempts = chat_json(messages)

    # Kontrola słownictwa: mały model myli podobne słowa ("zęzowa" -> "zębowa"/"bilgowa") i podmienia
    # pomieszczenia ("maszynownia" -> "siłownia"). To zmienia sens zgłoszenia, więc dajemy jedną poprawkę.
    problems = term_problems(stt.text, out["tresc"]) if not out["niejednoznaczne"] else []
    got_lang = guess_language(out["tresc"])
    if target_lang in ("pl", "en") and got_lang and got_lang != target_lang and not out["niejednoznaczne"]:
        problems.append(f"`tresc` must be written in '{target_lang}', not '{got_lang}'.")
    if problems:
        log.info("kontrola słownictwa: %s - poprawka", "; ".join(problems))
        fix_msgs = messages + [
            {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
            {"role": "user", "content": "Fix `tresc`: " + " ".join(problems) +
                                        " Keep everything else. Return the corrected JSON only."},
        ]
        fixed, more = chat_json(fix_msgs)
        attempts += more
        def count(o: dict) -> int:
            n = len(term_problems(stt.text, o["tresc"]))
            g = guess_language(o["tresc"])
            return n + (1 if target_lang in ("pl", "en") and g and g != target_lang else 0)
        if not fixed["niejednoznaczne"] and count(fixed) < count(out):
            out = fixed
    # Mały model czasem uznaje konkretną wypowiedź za pustą. Jeśli po usunięciu wypełniaczy zostaje
    # kilka słów treści, prosimy jeszcze raz - "dopytaj zgłaszającego" przy konkretnej treści to strata czasu załogi.
    if out["niejednoznaczne"] and _content_words(stt.text) >= 6:
        log.info("model uznał wypowiedź za niejednoznaczną mimo treści - ponawiam")
        messages = messages + [
            {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
            {"role": "user", "content": "The speech DOES contain concrete information (places, equipment or work done). "
                                        "Set niejednoznaczne to false and write `tresc` with that information."},
        ]
        retry, more = chat_json(messages)
        if not retry["niejednoznaczne"]:
            out = retry
        attempts += more
    return out, attempts


# (rdzeń w nagraniu, jak go zapisać) - jeśli rdzeń padł w nagraniu, musi być też w `tresc`
KEY_TERMS = [
    ("zęz", "zęza / zęzowy"), ("balast", "balast / balastowy"), ("kingston", "kingston"),
    ("maszynowni", "maszynownia"), ("siłowni", "siłownia"), ("ładowni", "ładownia"), ("pentr", "pentra"),
    ("mes", "mesa"), ("separator", "separator"), ("wyparown", "wyparownik"), ("sprężark", "sprężarka"),
    ("bosman", "bosman"), ("chief", "chief"), ("kapitan", "kapitan"),
    ("trap", "trap"), ("topow", "światło topowe"),
]

_PL_HINT = re.compile(r"[ąćęłńśźż]|\b(?:jest|nie|się|oraz|został[aoy]?|należy|do|na|przy|i|w|z)\b", re.I)
_EN_HINT = re.compile(r"\b(?:the|is|are|was|were|has|have|and|to|of|on|at|with|been|will)\b", re.I)


def guess_language(text: str) -> Optional[str]:
    """Bardzo prosta ocena: 'pl' / 'en' / None (gdy nie wiadomo)."""
    pl, en = len(_PL_HINT.findall(text)), len(_EN_HINT.findall(text))
    if pl >= 2 and pl > en:
        return "pl"
    if en >= 2 and en > pl:
        return "en"
    return None
# kalki / pomyłki, których nie ma w nagraniu -> czym je zastąpić
FALSE_FRIENDS = [("bilg", "zęz", "write 'zęza'/'zęzowy' (Polish), never 'bilge'/'bilgowy'"),
                 ("zęb", "zęz", "the speaker said 'zęzowy' (bilge), not 'zębowy' (gear)")]


def term_problems(raw: str, tresc: str) -> list[str]:
    """Kluczowe słowa z nagrania, których brakuje w `tresc`, i kalki, których w nagraniu nie było (tylko PL)."""
    r, t = raw.lower(), tresc.lower()
    problems = []
    for wrong, right_stem, hint in FALSE_FRIENDS:
        if wrong in t and wrong not in r and right_stem in r:
            problems.append(f"Do not use '{wrong}...': {hint}.")
    for stem, word in KEY_TERMS:
        if re.search(rf"\b{stem}", r) and not re.search(rf"\b{stem}", t):
            problems.append(f"The speaker said '{word}' - keep this word, do not replace it.")
    # numer urządzenia ("nr 10", "No. 3"), którego w nagraniu nie było = wymyślony
    spoken = _spoken_numbers(raw)
    for num in sorted(set(re.findall(r"\b(?:nr|no\.?|number|numer)\s*(\d+)", t))):
        if num not in spoken:
            problems.append(f"The speaker never said number {num} - remove 'nr/No. {num}' unless it was said.")
    return problems


_ORDINAL_WORDS = {"jedynka": 1, "dwójka": 2, "dwojka": 2, "trójka": 3, "trojka": 3, "czwórka": 4, "czworka": 4,
                  "piątka": 5, "piatka": 5, "szóstka": 6, "szostka": 6, "jedynce": 1, "dwójce": 2, "trójce": 3,
                  "jedynki": 1, "dwójki": 2, "trójki": 3, "trójkę": 3, "dwójkę": 2, "jedynkę": 1}


def _spoken_numbers(raw: str) -> set[str]:
    """Wszystkie liczby z nagrania: cyfry, liczebniki (też pojedyncze słowa) i 'jedynka/dwójka/trójka'."""
    text = normalize_numbers(raw).lower()
    nums = set(re.findall(r"\d+", text))
    polish = bool(re.search(r"[ąćęłńóśźż]", text))
    for w in re.findall(r"\w+", text):
        if w == "ten" and polish:  # polskie "ten" = "this", nie 10
            continue
        if w in _NUM_WORDS:
            nums.add(str(_NUM_WORDS[w][0]))
        elif w in _ORDINAL_WORDS:
            nums.add(str(_ORDINAL_WORDS[w]))
    return nums


def _content_words(text: str) -> int:
    t = _FILLERS.sub(" ", text.replace("*", " "))
    return len([w for w in re.findall(r"\w+", t) if len(w) > 2])


# --- tryb MOCK: proste czyszczenie bez LLM (do testów integracji STT <-> parser <-> decyzja) ---
_FILLERS = re.compile(
    r"\b(?:y+|e+|eh+|ah+|ahh+|hmm+|yyy+|eee+|no to tak|no więc|no to|znaczy|kurde|wiesz|jakby|sir)\b[,.]*\s*",
    re.IGNORECASE,
)


def mock_clean(stt: STTInput) -> tuple[dict, int]:
    t = _FILLERS.sub("", normalize_numbers(stt.text))
    t = re.sub(r"\s*\.{2,}\s*", " ", t).strip(" ,.")
    lang = stt.language or ("pl" if re.search(r"[ąćęłńóśźż]|\b(?:jest|się|nie|na|do)\b", t, re.I) else "en")
    unclear = len(t.split()) < 3
    return {"jezyk": lang, "tresc": _plain_text(t[:1].upper() + t[1:]) if not unclear else "",
            "niejednoznaczne": unclear}, 1


# ==========================================
# SKŁADANIE ZGŁOSZENIA
# ==========================================

def watch_of(hour: int) -> str:
    """Tak samo jak shipdec.generate.watch_of: 0-4, 4-8, ... -> '00-04', '04-08', ..."""
    start = hour // 4 * 4
    return f"{start:02d}-{start + 4:02d}"


def _parse_time(value: Optional[str], fallback: datetime) -> datetime:
    if value:
        try:
            ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        except ValueError:
            log.warning("niepoprawny czas_utc %r - używam czasu odbioru", value)
    return fallback


def process(stt: STTInput) -> Zgloszenie:
    started = time.perf_counter()
    received = datetime.now(timezone.utc).replace(microsecond=0)
    ts = _parse_time(stt.czas_utc, received).astimezone(timezone.utc)

    if LLM_MOCK:
        out, attempts = mock_clean(stt)
        model = "mock"
    else:
        out, attempts = call_llm(stt)
        model = LLM_MODEL

    lang = _norm_lang(out["jezyk"], stt.language)
    tresc = out["tresc"]
    if out["niejednoznaczne"]:
        text_lang = lang if SUMMARY_LANGUAGE == "auto" else SUMMARY_LANGUAGE
        tresc = UNCLEAR_TEXT.get(text_lang, UNCLEAR_TEXT["en"])

    result = Zgloszenie(
        id=stt.id or f"ZGL-{ts:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}",
        statek=stt.statek or SHIP_NAME,
        czas_utc=ts.isoformat(timespec="seconds"),
        wachta=stt.wachta or watch_of(ts.hour),
        zglaszajacy=stt.zglaszajacy,
        lokalizacja=stt.lokalizacja,
        kanal=stt.kanal or "glos",
        urzadzenie=stt.urzadzenie,
        jezyk=lang,
        nagranie_s=stt.nagranie_s,
        tresc=tresc,
        tresc_surowa=stt.text,
        niejednoznaczne=out["niejednoznaczne"],
        porzadkowanie=Porzadkowanie(
            model=model, czas_ms=int((time.perf_counter() - started) * 1000),
            proby=attempts, stt_pewnosc=stt.stt_confidence,
        ),
    )
    log.info("[%s] %s%s %dms: %s", result.id, result.jezyk, " NIEJEDNOZNACZNE" if result.niejednoznaczne else "",
             result.porzadkowanie.czas_ms, result.tresc[:120])
    return result


def forward_to_decision_model(payload: dict) -> None:
    try:
        r = httpx.post(DECISION_URL, json=payload, timeout=DECISION_TIMEOUT)
        r.raise_for_status()
        log.info("[%s] przekazano do modelu decyzyjnego -> HTTP %d", payload["id"], r.status_code)
    except Exception as exc:  # nie wywracamy odpowiedzi do STT, jeśli model decyzyjny leży
        log.error("[%s] przekazanie do %s nie powiodło się: %s", payload["id"], DECISION_URL, exc)


async def handle(stt: STTInput, background: BackgroundTasks, forward: bool) -> Zgloszenie:
    try:
        result = await run_in_threadpool(process, stt)
    except LLMUnavailable as exc:
        log.error("%s", exc)
        raise HTTPException(503, ErrorBody(error="llm_unavailable", message=str(exc), id=stt.id).model_dump())
    except LLMBadOutput as exc:
        log.error("%s", exc)
        raise HTTPException(502, ErrorBody(error="llm_bad_output", message=str(exc), id=stt.id).model_dump())
    if forward and DECISION_URL:
        background.add_task(forward_to_decision_model, result.model_dump(mode="json"))
    return result


# ==========================================
# ENDPOINTY
# ==========================================

@app.get("/health")
def health(deep: bool = False):
    """deep=true sprawdza też, czy serwer LLM odpowiada i ma model."""
    info = {"status": "ok", "model": "mock" if LLM_MOCK else LLM_MODEL, "llm_url": LLM_BASE_URL,
            "parser_version": PARSER_VERSION, "report_schema_version": REPORT_SCHEMA_VERSION,
            "summary_language": SUMMARY_LANGUAGE, "decision_url": DECISION_URL or None}
    if deep and not LLM_MOCK:
        try:
            models = [m.id for m in client.with_options(timeout=5).models.list()]
            info["llm_reachable"] = True
            info["model_available"] = LLM_MODEL in models
            if LLM_MODEL not in models:
                info["status"] = "degraded"
        except Exception as exc:
            info.update(status="degraded", llm_reachable=False, llm_error=str(exc))
    return info


@app.get("/schema")
def schema():
    """JSON Schema zgłoszenia wysyłanego do modelu decyzyjnego."""
    return Zgloszenie.model_json_schema()


@app.post("/parse", response_model=Zgloszenie,
          responses={502: {"model": ErrorBody}, 503: {"model": ErrorBody}})
async def parse_stt(payload: STTInput, background: BackgroundTasks, forward: bool = True):
    """Wypowiedź z STT (JSON) -> zgłoszenie dla modelu decyzyjnego."""
    return await handle(payload, background, forward)


@app.post("/parse/text", response_model=Zgloszenie,
          responses={502: {"model": ErrorBody}, 503: {"model": ErrorBody}})
async def parse_plain_text(request: Request, background: BackgroundTasks, forward: bool = True):
    """Dla najprostszych STT: surowy tekst w body (Content-Type: text/plain)."""
    body = (await request.body()).decode("utf-8", errors="replace")
    try:
        stt = STTInput(text=body)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False))
    return await handle(stt, background, forward)


if __name__ == "__main__":
    import uvicorn

    log.info("Start: model=%s llm=%s mock=%s jezyk=%s decision_url=%s port=%d",
             LLM_MODEL, LLM_BASE_URL, LLM_MOCK, SUMMARY_LANGUAGE, DECISION_URL or "-", PORT)
    uvicorn.run(app, host=HOST, port=PORT)
