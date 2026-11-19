"""Worker statku na atrapie Supabase: przebieg zdarzeń jak w supabase/README.md."""
from datetime import datetime, timedelta, timezone

from shipdec.backends import MockBackend
from shipdec.config import load_questions
from shipdec.contract import to_decision
from shipdec.ship import SECTOR_LABELS
from shipdec.worker import Pipeline, Worker, autopilot


class FakeSupabase:
    def __init__(self):
        self.tables = {"events": [], "crew": [], "ship_status": [{"id": 1, "autopilot": True}]}
        self.files = {}

    @staticmethod
    def _match(row, key, cond):
        if key in ("select", "order", "limit"):
            return True
        val = row.get("payload", {}).get(key.split("->>")[1]) if "->>" in key else row.get(key)
        op, arg = cond.split(".", 1)
        if op == "eq":
            return str(val).lower() == arg.lower() if isinstance(val, bool) else str(val) == arg
        if op == "in":
            return str(val) in [x.strip('"') for x in arg.strip("()").split(",")]
        if op == "gte":
            return str(val) >= arg
        raise NotImplementedError(op)

    def select(self, table, **params):
        rows = [r for r in self.tables[table] if all(self._match(r, k, v) for k, v in params.items())]
        if params.get("order", "").startswith("on_duty.desc"):
            rows.sort(key=lambda r: not r.get("on_duty"))
        return rows[: int(params["limit"])] if "limit" in params else rows

    def insert(self, table, row):
        row = dict(row)
        row.setdefault("ts", datetime.now(timezone.utc).isoformat())
        self.tables[table].append(row)

    def update(self, table, values, **filters):
        for r in self.select(table, **filters):
            r.update(values)

    def download(self, bucket, path):
        return self.files[(bucket, path)]


class FakePipeline(Pipeline):
    def __init__(self, transcripts):
        self.transcripts = transcripts
        self.basal = MockBackend(seed=1)
        self.questions, self.thresholds = load_questions()

    def stt(self, audio, filename):
        return self.transcripts[audio]

    def clean(self, text):
        unclear = text.strip().lower().startswith("yyy nic")
        return {"text_en": "Cooling water pump No. 2: leak at mechanical seal.", "lang": "pl", "unclear": unclear}


def _setup():
    sb = FakeSupabase()
    sb.tables["crew"] += [{"actor": "2nd_engineer:tom", "position": "2nd_engineer", "on_duty": False, "name": "Tom"},
                          {"actor": "2nd_engineer:mateusz", "position": "2nd_engineer", "on_duty": True, "name": "Mateusz"},
                          {"actor": "chief_officer:ivan", "position": "chief_officer", "on_duty": True, "name": "Ivan"}]
    return sb


def _record(sb, rid, audio, path=None):
    path = path or f"uid/{rid}.webm"
    sb.files[("recordings", path)] = audio
    sb.insert("events", {"event_id": rid, "report_id": rid, "type": "report.recorded", "actor": "2nd_engineer:mateusz",
                         "payload": {"audio_path": path, "mime": "audio/webm", "station": "engine"}})


def _types(sb, rid):
    return [e["type"] for e in sb.tables["events"] if e["report_id"] == rid]


def test_recording_becomes_transcribed_and_structured_with_basal_decision():
    sb = _setup()
    _record(sb, "r1", b"A1")
    w = Worker(sb, FakePipeline({b"A1": "pompa dwa cieknie z uszczelnienia"}), datetime.now(timezone.utc) - timedelta(minutes=5))
    assert w.tick() == 1
    assert _types(sb, "r1") == ["report.recorded", "report.transcribed", "report.structured"]
    tr = sb.tables["events"][1]
    assert tr["payload"] == {"text": "pompa dwa cieknie z uszczelnienia", "lang": "pl"} and tr["actor"] == "system:whisper"
    form = sb.tables["events"][2]["payload"]
    for k in ("equipment", "sfi_code", "priority", "text_en", "lang_original", "missing_fields", "confidence"):
        assert k in form                                         # ReportForm z frontend/src/types.ts
    assert form["priority"] in (1, 2, 3) and form["missing_fields"] == []          # -> pending_approval
    assert form["location"] in SECTOR_LABELS.values()
    d = form["decision"]
    assert d["department"] in ("engine", "deck", "catering") and d["position"]
    if d["position"] == "2nd_engineer":
        assert d["assignee"] == "2nd_engineer:mateusz"           # najpierw ktoś na dyżurze
    # drugi tick i restart workera niczego nie dublują
    assert w.tick() == 0
    w2 = Worker(sb, w.pipe, w.since)
    w2.tick()
    assert len(_types(sb, "r1")) == 3


def test_empty_recording_asks_again_and_answer_restructures():
    sb = _setup()
    _record(sb, "r2", b"A2")
    pipe = FakePipeline({b"A2": "", b"A3": "pompa numer dwa, cieknie"})
    w = Worker(sb, pipe, datetime.now(timezone.utc) - timedelta(minutes=5))
    w.tick()
    assert _types(sb, "r2") == ["report.recorded", "report.clarification_requested"]
    sb.files[("recordings", "uid/r2-answer-1.webm")] = b"A3"
    sb.insert("events", {"event_id": "ans1", "report_id": "r2", "type": "report.clarification_answered",
                         "actor": "2nd_engineer:mateusz", "payload": {"audio_path": "uid/r2-answer-1.webm"}})
    w.tick()
    assert _types(sb, "r2")[-3:] == ["report.clarified", "report.transcribed", "report.structured"]
    w.tick()
    assert _types(sb, "r2").count("report.clarified") == 1


def test_no_content_is_a_clarification_not_a_form():
    sb = _setup()
    _record(sb, "r3", b"A4")
    Worker(sb, FakePipeline({b"A4": "yyy nic, wszystko dobrze"}), datetime.now(timezone.utc) - timedelta(minutes=5)).tick()
    assert _types(sb, "r3") == ["report.recorded", "report.transcribed", "report.clarification_requested"]


def test_take_over_switches_autopilot_off():
    sb = _setup()
    assert autopilot(sb, False) is True and autopilot(sb) is False


def test_old_reports_are_ignored():
    sb = _setup()
    _record(sb, "old", b"A1")
    sb.tables["events"][-1]["ts"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    w = Worker(sb, FakePipeline({b"A1": "x"}), datetime.now(timezone.utc) - timedelta(minutes=10))
    assert w.tick() == 0


def test_form_maps_decision_fields():
    from shipdec.worker import build_form
    q, th = load_questions()
    dec = to_decision(MockBackend(seed=2).decide("lina na rufie przetarta", q)["answers"], th, {})
    f = build_form("Mooring rope at aft: badly chafed, needs replacing.", "pl", dec, "bosun:jun")
    assert f["equipment"] == "Mooring rope at aft" and f["decision"]["assignee"] == "bosun:jun"
