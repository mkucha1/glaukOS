"""Testy potoku na atrapie modelu — nie wymagają GPU ani Basala."""
import json

from shipdec.backends import MockBackend
from shipdec.config import load_questions
from shipdec.evaluate import MODEL_INPUT_FIELD, run, summarize
from shipdec.generate import generate, load_dataset, write_dataset


def test_generate_is_deterministic():
    assert generate(20, seed=1) == generate(20, seed=1)


def test_gold_labels_match_question_options():
    questions, _ = load_questions()
    _, labels = generate(100, seed=2)
    for lab in labels:
        g = lab["gold"]
        assert g["dzial"] in questions["dzial"]["criteria"]
        assert g["osoba"] in questions["osoba"]["criteria"]
        assert 1 <= g["pilnosc"] <= len(questions["pilnosc"]["criteria"])
        assert isinstance(g["raport_dpa"], bool)


def test_report_has_metadata_and_no_gold():
    reports, _ = generate(50, seed=4)
    for r in reports:
        for key in ("id", "czas_utc", "wachta", "zglaszajacy", "lokalizacja", "jezyk", "tresc"):
            assert key in r
        assert "gold" not in r


def test_one_file_per_report_roundtrip(tmp_path):
    reports, labels = generate(15, seed=6)
    rep_dir = write_dataset(reports, labels, tmp_path)
    assert len(list(rep_dir.glob("*.json"))) == 15
    assert json.loads((rep_dir / f"{reports[0]['id']}.json").read_text(encoding="utf-8")) == reports[0]
    assert load_dataset(tmp_path) == (reports, labels)


class SpyBackend(MockBackend):
    def __init__(self):
        super().__init__()
        self.states = []

    def decide(self, state, questions):
        self.states.append(state)
        return super().decide(state, questions)


def test_model_gets_only_report_text():
    questions, thresholds = load_questions()
    reports, labels = generate(30, seed=3)
    spy = SpyBackend()
    summary = summarize(run(reports, labels, questions, spy), thresholds)
    assert spy.states == [r[MODEL_INPUT_FIELD] for r in reports]
    assert set(summary) == set(questions)


def test_gold_map_and_api_strip():
    from shipdec.config import api_questions, gold_key
    q = {"pilnosc": {"type": "score", "instructions": "x", "criteria": ["a", "b", "c"],
                     "gold_map": {1: 1, 2: 1, 3: 2, 4: 3, 5: 3}}}
    assert [gold_key(q["pilnosc"], v) for v in (1, 2, 3, 4, 5)] == ["0", "0", "1", "2", "2"]
    assert "gold_map" not in api_questions(q)["pilnosc"]


def test_mostly_routine_reports():
    _, labels = generate(1000, seed=11)
    share = sum(lab["kategoria"] == "rutyna" for lab in labels) / len(labels)
    assert 0.75 <= share <= 0.85


def test_report_level_summary_and_queue():
    from shipdec.evaluate import summarize_reports
    from shipdec.queue import order, priority
    questions, thresholds = load_questions()
    reports, labels = generate(40, seed=12)
    res = run(reports, labels, questions, MockBackend())
    rep = summarize_reports(res, thresholds)
    assert 0 <= rep["w_pelni_automatycznie"] <= 1
    q = order(res)
    prios = [priority(r) for r in q]
    assert prios == sorted(prios, reverse=True)
    for r in res:
        if r["decisions"]["raport_dpa"]["pred"] == "true":
            assert priority(r) == 3


def test_realistic_set_is_consistent(tmp_path):
    from shipdec.realistic import build, write
    questions, _ = load_questions()
    reports, labels = build()
    assert len(reports) >= 50 and len({r["id"] for r in reports}) == len(reports)
    for lab in labels:
        g = lab["gold"]
        assert g["dzial"] in questions["dzial"]["criteria"]
        assert g["osoba"] in questions["osoba"]["criteria"]
        assert 1 <= g["pilnosc"] <= len(questions["pilnosc"]["criteria"])
        assert lab.get("streszczenie_wzorcowe")
    for r in reports:
        assert "gold" not in r and "streszczenie_wzorcowe" not in r
    write(reports, labels, tmp_path)
    assert len(list((tmp_path / "reports").glob("*.json"))) == len(reports)
    assert (tmp_path / "kompresja.jsonl").exists()


def test_contract_adapter_with_mock():
    from shipdec.contract import ROLE_FROM_OSOBA, decide
    questions, thresholds = load_questions()
    out = decide("Na pompie chłodzenia cieknie uszczelka, ktoś prawie się poślizgnął.", MockBackend(),
                 questions, thresholds)
    assert out["priority"] in (1, 2, 3, 4, 5)
    assert set(out["decisions"]) == set(questions)
    assert set(ROLE_FROM_OSOBA) == set(questions["osoba"]["criteria"])
    if out["dpa_report"]:
        assert out["priority"] == 1


def test_settings_env_file(tmp_path, monkeypatch):
    from shipdec import settings
    env = tmp_path / ".env"
    env.write_text("# komentarz\nBASAL_URL=http://10.0.0.5:8000/v1/systemone\nSHIP_ID='mv-test'\n", encoding="utf-8")
    assert settings.read_env_file(env) == {"BASAL_URL": "http://10.0.0.5:8000/v1/systemone", "SHIP_ID": "mv-test"}
    monkeypatch.setenv("SHIP_ID", "z-srodowiska")
    assert settings.get("SHIP_ID") == "z-srodowiska"
