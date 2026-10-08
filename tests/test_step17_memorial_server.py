"""Step 17: memorial server — route contracts with mocked brain and TTS (offline)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import memoria.memorial_server as srv
import memoria.brain as brain
from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORIA_DATA", str(tmp_path))
    cfg = MemoriaConfig(data_dir=str(tmp_path))
    store = InterviewStore(cfg)
    p = store.create_person("Ruth", 1942)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots"])
    eng.answer("I grew up on a farm outside Salem.", tier="PUBLIC")
    eng.answer("My mother sang while she cooked.", tier="FAMILY")
    eng.answer("I was afraid of the dark as a child.", tier="PRIVATE")
    eng.pause()
    c = TestClient(srv.app)
    return c, p.id


def test_health(env):
    c, pid = env
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_people(env):
    c, pid = env
    r = c.get("/people")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "Ruth"


def test_ask_happy_path(env, monkeypatch):
    c, pid = env
    # mock the brain: a grounded answer citing the archive
    class FakeBrain:
        def __init__(self, persona): self.persona = persona
        def ask(self, q, k=4):
            return {"answer": "I grew up on a farm outside Salem.",
                    "refused": False, "grounded": True,
                    "retrieved": [{"answer_id": "ans_x", "question": "Where did you grow up?",
                                   "statement": "I grew up on a farm outside Salem.",
                                   "retrieval_score": 0.71}],
                    "grounding": {"grounded": True}}
    monkeypatch.setattr("memoria.memorial_server.MemorialBrain", FakeBrain)
    r = c.post("/ask", json={"person_id": pid, "question": "where did you grow up?",
                             "role": "public"})
    assert r.status_code == 200
    j = r.json()
    assert j["answer"].startswith("I grew up on a farm")
    assert j["citations"][0]["answer_id"] == "ans_x"
    assert j["refused"] is False


def test_ask_role_tiers_the_corpus(env, monkeypatch):
    c, pid = env
    captured = {}
    class FakeBrain:
        def __init__(self, persona): self.persona = persona; captured["persona"] = persona
        def ask(self, q, k=4): return {"answer": "x", "refused": False, "grounded": True,
                                       "retrieved": [], "grounding": {"grounded": True}}
    monkeypatch.setattr("memoria.memorial_server.MemorialBrain", FakeBrain)
    c.post("/ask", json={"person_id": pid, "question": "q?", "role": "public"})
    assert all(s["tier"] == "PUBLIC" for s in captured["persona"]["corpus"])
    assert len(captured["persona"]["corpus"]) == 1
    c.post("/ask", json={"person_id": pid, "question": "q?", "role": "family"})
    assert len(captured["persona"]["corpus"]) == 2
    c.post("/ask", json={"person_id": pid, "question": "q?", "role": "executor",
                         "executor_key": "k"})
    assert len(captured["persona"]["corpus"]) == 3


def test_ask_requires_executor_key(env):
    c, pid = env
    r = c.post("/ask", json={"person_id": pid, "question": "q?", "role": "executor"})
    assert r.status_code == 401


def test_ask_rejects_unknown_role(env):
    c, pid = env
    r = c.post("/ask", json={"person_id": pid, "question": "q?", "role": "stranger"})
    assert r.status_code == 400


def test_ask_missing_person(env):
    c, pid = env
    r = c.post("/ask", json={"person_id": "person_nope", "question": "q?"})
    assert r.status_code == 404


def test_timeline_tier_filtered(env):
    c, pid = env
    r = c.get(f"/timeline?person_id={pid}&role=public")
    assert r.status_code == 200
    ch = r.json()
    n_public = sum(len(v) for v in ch.values())
    assert n_public == 1
    r2 = c.get(f"/timeline?person_id={pid}&role=family")
    n_family = sum(len(v) for v in r2.json().values())
    assert n_family == 2
    r3 = c.get(f"/timeline?person_id={pid}&role=executor&executor_key=x")
    # executor without key fails at the route level (executor requires key)
    assert r3.status_code == 401


def test_letters_gated(env):
    c, pid = env
    from memoria.letters import LetterBox
    from memoria.config import load_config
    box = LetterBox(load_config())
    box.write(pid, "the world", "Thank you for visiting.", tier="PUBLIC",
              open_rule="on-date", open_date="2020-01-01")
    box.write(pid, "family", "The porch key.", tier="FAMILY")
    r = c.get(f"/letters?person_id={pid}&role=public")
    assert len(r.json()) == 1
    r2 = c.get(f"/letters?person_id={pid}&role=family")
    assert len(r2.json()) == 2


def test_letter_unlock_route(env):
    c, pid = env
    from memoria.letters import LetterBox
    from memoria.config import load_config
    cfg = load_config()
    box = LetterBox(cfg)
    l = box.write(pid, "daughter", "I was always proud of you.")
    r = c.post("/letter/unlock", json={"person_id": pid, "letter_id": l.id,
                                       "executor_key": "wrong"})
    assert r.json()["sealed"] is True     # wrong key: still sealed
    r2 = c.post("/letter/unlock", json={"person_id": pid, "letter_id": l.id,
                                        "executor_key": cfg.executor_key})
    assert r2.json()["sealed"] is False
    assert r2.json()["body"].startswith("I was always proud")

