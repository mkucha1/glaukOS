"""Testy potoku na atrapie modelu — nie wymagają GPU ani Basala."""
import json
import uuid

from shipdec.backends import MockBackend
from shipdec.config import ROOT, load_crew, load_questions, load_yaml
from shipdec.evaluate import MODEL_INPUT_FIELD, run, summarize, summarize_reports
from shipdec.generate import generate, load_dataset, write_dataset
from shipdec.ship import SECTORS, sector_of

SERVER = ROOT.parents[1] / "mozg-statku" / "server"
# Bez serwera w repo (gałąź decision-layer) — kopia crew.json z integration/mozg-statku/.
SERVER_CREW = (SERVER / "config" / "crew.json") if SERVER.is_dir() else ROOT / "integration" / "mozg-statku" / "crew.json"


def test_generate_is_deterministic():
    assert generate(20, seed=1) == generate(20, seed=1)


def test_gold_labels_match_question_options():
    questions, _ = load_questions()
    _, labels = generate(200, seed=2)
    for lab in labels:
        g = lab["gold"]
        assert g["dzial"] in questions["dzial"]["criteria"]
        assert g["osoba"] in questions["osoba"]["criteria"]
        assert 1 <= g["pilnosc"] <= len(questions["pilnosc"]["criteria"])
        assert isinstance(g["raport_dpa"], bool)


def test_report_matches_server_text_api_and_has_meta():
    reports, _ = generate(50, seed=4)
    for r in reports:
        uuid.UUID(r["report_id"])                     # serwer: ID nadaje urządzenie, UUID
        for key in ("crew_id", "text", "lang", "recorded_at"):
            assert r[key]
        assert "gold" not in r
        assert r["_meta"]["sector"] in SECTORS


def test_one_file_per_report_roundtrip(tmp_path):
    reports, labels = generate(15, seed=6)
    rep_dir = write_dataset(reports, labels, tmp_path)
    assert len(list(rep_dir.glob("*.json"))) == 15
    assert json.loads((rep_dir / f"{reports[0]['report_id']}.json").read_text(encoding="utf-8")) == reports[0]
    assert load_dataset(tmp_path) == (reports, labels)


def test_mostly_routine_reports():
    _, labels = generate(1000, seed=11)
    share = sum(lab["kategoria"] == "rutyna" for lab in labels) / len(labels)
    assert 0.75 <= share <= 0.85


# ------------------------------------------------------------------ zgodność z frontendem i serwerem
def test_sector_rules_match_frontend_examples():
    # przykłady z frontend/src/lib/seed.ts (lokalizacja -> sektor wg ship.ts)
    assert sector_of("Purifier room") == "purifier"
    assert sector_of("Engine control room") == "ecr"
    assert sector_of("Steering gear room") == "steering"
    assert sector_of("Bridge wing, starboard") == "bridge"
    assert sector_of("Galley, provision store") == "galley"
    assert sector_of("Cabin 204, accommodation deck B") == "cabins"
    assert sector_of("Forecastle") == "bow"
    assert sector_of("Main deck, hatch 3") == "deck"
    assert sector_of("Cargo hold 2") == "holds"
    assert sector_of("Double bottom, ballast tank 3P") == "tanks"
    assert sector_of("Engine room, lower platform") == "engine"


def test_templates_cover_every_ship_sector():
    templates = load_yaml(ROOT / "data" / "templates" / "reports.yaml")["templates"]
    covered = {sector_of(m) for t in templates for m in t["miejsca"]}
    assert covered == set(SECTORS)


def test_all_locations_are_english_and_land_in_a_sector():
    templates = load_yaml(ROOT / "data" / "templates" / "reports.yaml")["templates"]
    utter = load_yaml(ROOT / "data" / "realistic" / "utterances.yaml")["wypowiedzi"]
    places = [m for t in templates for m in t["miejsca"]] + [u["lokalizacja"] for u in utter]
    for p in places:
        assert not any(ch in p for ch in "ąćęłńóśźż"), p


FRONTEND_ROLES = {"2nd_engineer", "chief_engineer", "officer"}   # frontend/src/types.ts: Role


def test_frontend_roles_are_read_from_frontend():
    types = (ROOT.parents[1] / "frontend" / "src" / "types.ts").read_text()
    line = next(l for l in types.splitlines() if l.startswith("export type Role ="))
    assert {r.strip(" '") for r in line.split("=", 1)[1].rstrip(";").split("|")} == FRONTEND_ROLES


def test_roles_and_assignees_match_frontend_and_server():
    server_crew = {c["crew_id"]: c for c in json.loads(SERVER_CREW.read_text())}
    roster = {c["crew_id"]: c for c in load_yaml(ROOT / "config" / "roster.yaml")["zaloga"]}
    for c in roster.values():                              # zgłaszający = osoby z serwera w rolach z frontendu
        assert c["rola"] in FRONTEND_ROLES
        assert c["crew_id"] in server_crew and server_crew[c["crew_id"]]["role"] == c["rola"]
    assert set(load_crew()) == FRONTEND_ROLES              # pytanie `osoba` = role z frontendu
    for role, d in load_crew().items():
        assert server_crew[d["crew_id"]]["role"] == role


def test_reporter_roles_exist_in_roster():
    roles = {c["rola"] for c in load_yaml(ROOT / "config" / "roster.yaml")["zaloga"]}
    templates = load_yaml(ROOT / "data" / "templates" / "reports.yaml")["templates"]
    utter = load_yaml(ROOT / "data" / "realistic" / "utterances.yaml")["wypowiedzi"]
    assert {r for t in templates for r in t["zglaszajacy"]} <= roles
    assert {u["stanowisko"] for u in utter} <= roles


def test_server_decision_config_is_up_to_date():
    from shipdec.contract import SERVER_CONFIG, server_config
    on_disk = json.loads(SERVER_CONFIG.read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(server_config())), "uruchom: shipdec export-server-config"


# ------------------------------------------------------------------ potok i decyzje
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


def test_report_level_summary_and_queue():
    from shipdec.queue import order, priority
    questions, thresholds = load_questions()
    reports, labels = generate(40, seed=12)
    res = run(reports, labels, questions, MockBackend())
    rep = summarize_reports(res, thresholds)
    assert 0 <= rep["w_pelni_automatycznie"] <= 1
    prios = [priority(r) for r in order(res)]
    assert prios == sorted(prios)                          # P1 pierwsze


def test_gold_map_and_api_strip():
    from shipdec.config import api_questions, gold_key
    q = {"pilnosc": {"type": "score", "instructions": "x", "criteria": ["a", "b", "c"],
                     "gold_map": {1: 1, 2: 1, 3: 2, 4: 3, 5: 3}}}
    assert [gold_key(q["pilnosc"], v) for v in (1, 2, 3, 4, 5)] == ["0", "0", "1", "2", "2"]
    assert "gold_map" not in api_questions(q)["pilnosc"]


def test_contract_to_server_decision():
    from shipdec.contract import decide
    questions, thresholds = load_questions()
    for seed_text in ("Pompa chłodzenia, przeciek na uszczelnieniu, ktoś prawie się poślizgnął.",
                      "Lina na rufie przetarta.", "Obchód zrobiony, wszystko w normie."):
        out = decide(seed_text, MockBackend(), questions, thresholds)
        assert out["priority"] in (1, 2, 3)                # skala frontendu, P1 = najwyższy
        assert out["dept"] in ("engine", "deck")
        assert out["route_role"] in FRONTEND_ROLES
        assert isinstance(out["needs_officer"], bool)
        if out["_basal"]["dpa_report"]:
            assert out["priority"] == 1


def test_priority_mapping_p1_is_most_urgent():
    from shipdec.config import gold_key
    from shipdec.contract import PRIORITY_FROM_LEVEL
    questions, _ = load_questions()
    p = questions["pilnosc"]
    for prio in (1, 2, 3):                                 # etykieta P -> klucz Basala -> z powrotem P
        assert PRIORITY_FROM_LEVEL[int(gold_key(p, prio)) + 1] == prio
    assert p["criteria"][-1].startswith("P1")              # najwyższy poziom skali Basala = P1


def test_realistic_set_is_consistent(tmp_path):
    from shipdec.realistic import build, write
    questions, _ = load_questions()
    reports, labels = build()
    assert len(reports) >= 50 and len({r["report_id"] for r in reports}) == len(reports)
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


def test_settings_env_file(tmp_path, monkeypatch):
    from shipdec import settings
    env = tmp_path / ".env"
    env.write_text("# komentarz\nBASAL_URL=http://10.0.0.5:8001/v1/systemone\nSHIP_ID='mv-test'\n", encoding="utf-8")
    assert settings.read_env_file(env) == {"BASAL_URL": "http://10.0.0.5:8001/v1/systemone", "SHIP_ID": "mv-test"}
    monkeypatch.setenv("SHIP_ID", "z-srodowiska")
    assert settings.get("SHIP_ID") == "z-srodowiska"


def test_sector_question_uses_four_main_frontend_sectors():
    from shipdec.ship import MAIN_SECTORS, SECTOR_LABELS, SECTOR_MERGE, SECTORS, sector_of
    questions, thresholds = load_questions()
    assert list(questions["sektor"]["criteria"]) == MAIN_SECTORS and len(MAIN_SECTORS) <= 4
    assert set(SECTOR_MERGE) | set(MAIN_SECTORS) == set(SECTORS)        # każdy sektor frontendu ma miejsce
    for k in MAIN_SECTORS:                                              # etykieta -> ten sam sektor we frontendzie
        assert sector_of(SECTOR_LABELS[k]) == k
    assert thresholds.get("sektor") == 0.0


def test_reports_only_in_main_sectors(tmp_path):
    from shipdec.ship import MAIN_SECTORS
    from shipdec.generate import generate
    reports, labels = generate(n=60, seed=3)
    assert {r["_meta"]["sector"] for r in reports} <= set(MAIN_SECTORS)
    assert {l["gold"]["sektor"] for l in labels} <= set(MAIN_SECTORS)
