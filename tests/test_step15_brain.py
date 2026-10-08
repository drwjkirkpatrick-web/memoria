"""Step 15: memorial brain — retrieval, grounded generation, refusal paths (mocked servers)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import memoria.brain as brain
from memoria.brain import (MemorialBrain, retrieve, check_grounded, cosine,
                           embed_query, embed_doc, BrainError)


CORPUS = [
    {"answer_id": "a1", "question": "Where did you grow up?",
     "statement": "I grew up on a farm outside Salem. We had chickens.",
     "tier": "FAMILY", "answered_at": "2026-01-01"},
    {"answer_id": "a2", "question": "What was your earliest memory?",
     "statement": "The smell of rain on the dry fields, and my mother singing.",
     "tier": "FAMILY", "answered_at": "2026-01-01"},
    {"answer_id": "a3", "question": "What work did you do?",
     "statement": "I was a nurse for forty years, mostly night shifts.",
     "tier": "FAMILY", "answered_at": "2026-01-01"},
]


def test_cosine_basics():
    a = [1.0, 0.0]
    assert cosine(a, [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine(a, [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine(a, [-1.0, 0.0]) == pytest.approx(-1.0)
    assert cosine([0.0, 0.0], a) == 0.0


def test_retrieve_with_mock_embeddings(monkeypatch):
    # mock embeddings: orthogonal unit vectors per statement
    def fake_embed(texts, port=8091):
        vecs = []
        for t in texts:
            if "farm" in t or "chickens" in t:
                vecs.append([1.0, 0.0, 0.0])
            elif "rain" in t or "mother" in t:
                vecs.append([0.0, 1.0, 0.0])
            elif "nurse" in t:
                vecs.append([0.0, 0.0, 1.0])
            else:
                vecs.append([0.0, 0.0, 0.0])
        return vecs
    monkeypatch.setattr(brain, "embed", fake_embed)
    # query embedding: the "search:" query maps through the same mock
    hits = retrieve("search: where was the farm", CORPUS, k=2)
    assert len(hits) == 2
    assert hits[0]["answer_id"] == "a1"
    assert hits[0]["retrieval_score"] >= hits[1]["retrieval_score"]
    assert "answer_id" in hits[0] and "statement" in hits[0]


def test_retrieve_empty_corpus():
    assert retrieve("anything", [], k=4) == []


def test_check_grounded_accepts_traced():
    ctx = [{"statement": "I grew up on a farm outside Salem with chickens.",
            "question": "Where did you grow up?"}]
    ans = "I grew up on a farm outside Salem, and we kept chickens there."
    g = check_grounded(ans, ctx)
    assert g["grounded"] is True and g["ungrounded"] == []


def test_check_grounded_flags_invention():
    ctx = [{"statement": "I grew up on a farm outside Salem.",
            "question": "Where did you grow up?"}]
    ans = ("I grew up on a farm. "              # grounded
           "Later I flew helicopters in Alaska.")  # invented
    g = check_grounded(ans, ctx)
    assert g["grounded"] is False
    assert any("helicopters" in u for u in g["ungrounded"])


def test_check_grounded_empty_answer():
    g = check_grounded("", CORPUS)
    assert g["grounded"] is False


def test_brain_refuses_on_empty_corpus():
    persona = {"name": "Empty", "corpus": [], "system_prompt": "x"}
    mb = MemorialBrain(persona)
    r = mb.ask("where did you grow up?")
    assert r["refused"] is True
    assert "never spoke" in r["answer"] or "cannot tell" in r["answer"]
    assert r["retrieved"] == []


def test_brain_happy_path_mocked(monkeypatch):
    persona = {"name": "Ruth", "corpus": CORPUS,
               "system_prompt": "You are the memorial voice of Ruth."}

    def fake_retrieve(q, corpus, k=4, emb_port=8091):
        return [dict(corpus[0])]
    def fake_generate(prompt, question, context, gen_port=8090, max_tokens=400):
        return "I grew up on a farm outside Salem, and we kept chickens."
    monkeypatch.setattr(brain, "retrieve", fake_retrieve)
    monkeypatch.setattr(brain, "generate", fake_generate)
    mb = MemorialBrain(persona)
    r = mb.ask("where did you grow up?")
    assert r["refused"] is False
    assert r["grounded"] is True
    assert "farm" in r["answer"]
    assert r["retrieved"][0]["answer_id"] == "a1"


def test_brain_refuses_when_ungrounded(monkeypatch):
    persona = {"name": "Ruth", "corpus": CORPUS, "system_prompt": "x"}
    def fake_retrieve(q, corpus, k=4, emb_port=8091):
        return [dict(corpus[0])]
    def fake_generate(prompt, question, context, gen_port=8090, max_tokens=400):
        return "I grew up on a farm. I also captained a submarine in the war."
    monkeypatch.setattr(brain, "retrieve", fake_retrieve)
    monkeypatch.setattr(brain, "generate", fake_generate)
    mb = MemorialBrain(persona)
    r = mb.ask("where did you grow up?")
    assert r["refused"] is True          # drifted → refuse, keep raw for review
    assert "raw_answer" in r
    assert "submarine" in r["raw_answer"]
    assert "never spoke" in r["answer"] or "cannot tell" in r["answer"]


def test_servers_up_false_when_down():
    # no servers on these ports in test env (or if live, the flag is either)
    brain.EMB_PORT = 8099
    brain.GEN_PORT = 8098
    try:
        assert brain.servers_up() is False
    finally:
        brain.EMB_PORT = 8091
        brain.GEN_PORT = 8090
