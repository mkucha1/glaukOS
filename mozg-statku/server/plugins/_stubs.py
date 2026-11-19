"""Zaślepki (stuby) — działający, prosty odpowiednik modułów AI.

Dzięki nim cały przepływ demo (zgłoszenie -> przerobienie -> pytanie zwrotne -> czujnik
-> zatwierdzenie -> ląd) działa od pierwszej godziny, zanim modele będą gotowe. To też plan B
na scenę: `USE_STUBS=stt,brain` przełącza z powrotem na zaślepki bez zmiany kodu.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DEMO_SENTENCE = "Pompa chłodzenia, ciśnienie spada do 1,8 bara, przeciek na uszczelnieniu."
DEMO_ANSWER = "Dwa"

_PL_HINTS = re.compile(r"[ąćęłńóśźż]|\b(i|nie|jest|na|do|się|pompa|ciśnienie)\b", re.I)


def guess_lang(text: str) -> str:
    return "pl" if _PL_HINTS.search(text or "") else "en"


# =============================================================== STT (Mateusz)
def stt_transcribe(audio_path: str, lang_hint: str | None = None) -> dict:
    """Czyta transkrypt z pliku obok nagrania (<audio>.hint.txt), jeśli istnieje — do testów.
    W przeciwnym razie zwraca zdanie demo (albo „Dwa” dla odpowiedzi na pytanie zwrotne)."""
    p = Path(audio_path)
    hint = p.with_name(p.name + ".hint.txt")
    if hint.exists():
        text = hint.read_text(encoding="utf-8").strip()
    else:
        text = DEMO_ANSWER if p.name.startswith("clar-") else DEMO_SENTENCE
    return {"text": text, "lang": lang_hint or guess_lang(text), "duration_s": None, "model": "stub"}


# =============================================================== Brain (Maciej)
_NUM_WORDS = {
    "jeden": 1, "jedynka": 1, "jedna": 1, "pierwsza": 1, "pierwszy": 1, "one": 1, "first": 1,
    "dwa": 2, "dwójka": 2, "dwojka": 2, "druga": 2, "drugi": 2, "two": 2, "second": 2,
    "trzy": 3, "three": 3,
}
_YES = re.compile(r"\b(tak|yes|potwierdzam|zgadza|confirm|correct|ok)\b", re.I)

_DEFECTS = [
    (re.compile(r"pożar|ogień|pali się|fire", re.I), "fire", 5),
    (re.compile(r"dym|smoke", re.I), "smoke", 5),
    (re.compile(r"przeciek|wyciek|cieknie|leak", re.I), "leak", 4),
    (re.compile(r"wibrac|drga|vibrat", re.I), "abnormal vibration", 3),
    (re.compile(r"hałas|stuka|noise|knock", re.I), "abnormal noise", 3),
    (re.compile(r"przegrz|overheat", re.I), "overheating", 4),
]
_WHERE = [
    (re.compile(r"uszczelni|seal", re.I), "at mechanical seal"),
    (re.compile(r"kołnierz|flange", re.I), "at flange"),
    (re.compile(r"zawór|valve", re.I), "at valve"),
]


def _number_in(text: str) -> int | None:
    m = re.search(r"(?:nr|numer|no\.?|number|#)\s*(\d)", text, re.I)
    if m:
        return int(m.group(1))
    for w in re.findall(r"[a-ząćęłńóśźż]+", text.lower()):
        if w in _NUM_WORDS:
            return _NUM_WORDS[w]
    m = re.fullmatch(r"\s*(\d)\s*[.!]?\s*", text)
    return int(m.group(1)) if m else None


def _find_group(text: str, eq: dict) -> str | None:
    low = text.lower()
    for gid, g in eq.get("groups", {}).items():
        if any(a in low for a in g.get("aliases", [])):
            return gid
    return None


def _set_equipment(form: dict, item: dict) -> None:
    form["equipment"] = item["name"]
    form["sfi_code"] = item.get("sfi_code")
    form["location"] = item.get("location")
    form["_equipment_id"] = item["id"]


def _text_en(form: dict, group_name: str | None) -> str:
    what = form.get("equipment") or group_name or "Equipment"
    parts = [what]
    if form.get("value") is not None:
        verb = "dropping to" if form.get("_trend") == "down" else ("rising to" if form.get("_trend") == "up" else "at")
        parts.append(f"{form.get('parameter') or 'reading'} {verb} {form['value']:g} {form.get('unit') or ''}".strip())
    if form.get("defect"):
        parts.append(form["defect"])
    return ", ".join(parts) + "."


def brain_structure(text: str, lang: str, context: dict) -> dict:
    eq = context.get("equipment") or {}
    form: dict[str, Any] = {"lang_original": lang, "missing_fields": [], "priority": 3,
                            "action_taken": "none", "confidence": 0.6}
    gid = _find_group(text, eq)
    group = eq.get("groups", {}).get(gid or "", {})
    items = [e for e in eq.get("equipment", []) if e.get("group") == gid]
    no = _number_in(text)
    if gid:
        form["_group"] = gid
        match = [e for e in items if e.get("no") == no] if no else items
        if len(match) == 1:
            _set_equipment(form, match[0])
        else:
            form["missing_fields"].append("equipment_no")
            form["location"] = items[0].get("location") if items else None
    else:
        form["missing_fields"].append("equipment")

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(bar\w*|°\s*c|stopni\w*|deg\w*)", text, re.I)
    if m:
        form["value"] = float(m.group(1).replace(",", "."))
        form["unit"] = "bar" if m.group(2).lower().startswith("bar") else "°C"
        spec_items = items or eq.get("equipment", [])
        for it in spec_items:
            for pname, spec in it.get("sensors", {}).items():
                if spec.get("unit") == form["unit"]:
                    form["parameter"] = pname
                    break
            if form.get("parameter"):
                break
    else:
        form["missing_fields"].append("value")

    if re.search(r"spada|spadł|maleje|drop|falling|low", text, re.I):
        form["_trend"] = "down"
    elif re.search(r"rośnie|wzrasta|rising|high", text, re.I):
        form["_trend"] = "up"

    defects = []
    for rx, name, prio in _DEFECTS:
        if rx.search(text):
            defects.append(name)
            form["priority"] = max(form["priority"], prio)
    for rx, where in _WHERE:
        if rx.search(text) and defects:
            defects[-1] = f"{defects[-1]} {where}"
    form["defect"] = ", ".join(defects) or None
    form["text_en"] = _text_en(form, group.get("name_en"))
    form["confidence"] = 0.9 if not form["missing_fields"] else 0.6
    return form


def brain_check(form: dict, sensors: Any, context: dict) -> dict:
    eq = context.get("equipment") or {}
    crew = context.get("crew") or {}
    lang = crew.get("lang") or form.get("lang_original") or "en"
    lang = lang if lang in ("pl", "en") else "en"
    decision: dict[str, Any] = {"priority": form.get("priority", 3), "route_role": "chief_engineer",
                                "dept": "engine", "checks": [], "clarification": None, "notes": []}
    if decision["priority"] >= 5:
        decision["route_role"] = "master"

    if "equipment_no" in form.get("missing_fields", []):
        g = eq.get("groups", {}).get(form.get("_group") or "", {})
        ask = g.get("ask", {})
        decision["clarification"] = {"question": ask.get(lang) or ask.get("en") or "Which unit?",
                                     "question_en": ask.get("en"), "lang": lang, "field": "equipment_no"}
        return decision

    item = next((e for e in eq.get("equipment", []) if e["id"] == form.get("_equipment_id")), None)
    if item and form.get("value") is not None:
        spec = item["sensors"].get(form.get("parameter") or "") or next(iter(item["sensors"].values()), None)
        if spec:
            r = sensors.get(spec["tag"])
            measured = r["value"] if r else None
            ok = None if measured is None else abs(measured - form["value"]) <= spec.get("tolerance", 0)
            decision["checks"].append({"tag": spec["tag"], "parameter": form.get("parameter"),
                                       "reported": form["value"], "measured": measured,
                                       "unit": spec.get("unit"), "tolerance": spec.get("tolerance"),
                                       "ok": ok, "age_s": r.get("age_s") if r else None})
            if ok is False and not form.get("_value_confirmed"):
                q_pl = f"Czujnik pokazuje {measured:g} {spec['unit']}, a zgłoszono {form['value']:g}. Potwierdzasz odczyt?"
                q_en = f"Sensor shows {measured:g} {spec['unit']}, you reported {form['value']:g}. Do you confirm?"
                decision["clarification"] = {"question": q_pl if lang == "pl" else q_en,
                                             "question_en": q_en, "lang": lang, "field": "value"}
    return decision


def brain_apply_clarification(form: dict, clarification: dict, answer_text: str,
                              answer_lang: str, context: dict) -> dict:
    eq = context.get("equipment") or {}
    form = dict(form)
    field = (clarification or {}).get("field")
    missing = [f for f in form.get("missing_fields", [])]
    if field == "equipment_no":
        no = _number_in(answer_text or "")
        item = next((e for e in eq.get("equipment", [])
                     if e.get("group") == form.get("_group") and e.get("no") == no), None)
        if item:
            _set_equipment(form, item)
            missing = [f for f in missing if f != "equipment_no"]
    elif field == "value":
        m = re.search(r"(\d+(?:[.,]\d+)?)", answer_text or "")
        if m:
            form["value"] = float(m.group(1).replace(",", "."))
        if _YES.search(answer_text or "") or m:
            form["_value_confirmed"] = True
    form["missing_fields"] = missing
    form["confidence"] = 0.7 if not missing else 0.5  # trzeba było dopytać => mniejsza pewność
    group = eq.get("groups", {}).get(form.get("_group") or "", {})
    form["text_en"] = _text_en(form, group.get("name_en"))
    return form


# =============================================================== Przerobienie raportu (Daniel)
_FILLERS = re.compile(r"\b(y+|e+|yyy+|eee+|no więc|znaczy|jakby|kurczę|um+|uh+|like)\b[,.]?\s*", re.I)


def refine_text(text: str, lang: str, context: dict) -> dict:
    """Usuwa wtrącenia i nadmiarowe spacje, poprawia wielką literę i kropkę na końcu."""
    t = _FILLERS.sub("", text or "")
    t = re.sub(r"\s+", " ", t).strip(" ,")
    if t:
        t = t[0].upper() + t[1:]
        if t[-1] not in ".!?":
            t += "."
    return {"text": t, "lang": lang, "changes": ["stub: usunięto wtrącenia"] if t != (text or "").strip() else []}
