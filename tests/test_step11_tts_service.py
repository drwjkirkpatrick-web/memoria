"""Step 11: TTS service — contract tests with a fake engine (no model needed)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import memoria.tts_service as tts_service


class _FakeEngine:
    kind = "fake"

    def synth(self, text: str, voice: str) -> bytes:
        # deterministic fake audio: "FAKE" + text length as bytes
        return b"FAKEAUDIO" + len(text).to_bytes(4, "big")


@pytest.fixture
def client(tmp_path, monkeypatch):
    # data dir with a person
    from memoria.config import MemoriaConfig
    from memoria.interview import InterviewStore
    cfg = MemoriaConfig(data_dir=str(tmp_path))
    store = InterviewStore(cfg)
    p = store.create_person("Ruth", 1942)

    monkeypatch.setenv("MEMORIA_DATA", str(tmp_path))

    # force the fake engine
    tts_service._engine = _FakeEngine()
    tts_service._engine_kind = "fake"
    from fastapi.testclient import TestClient
    c = TestClient(tts_service.app)
    yield c, p.id
    tts_service._engine = None
    tts_service._engine_kind = None
    tts_service._cache.clear()


def test_health(client):
    c, pid = client
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["engine"] == "fake"


def test_synthesize_roundtrip(client):
    c, pid = client
    r = c.post("/synthesize", json={"person_id": pid, "text": "hello there"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content.startswith(b"FAKEAUDIO")
    # cache hit: identical request served from memory
    r2 = c.post("/synthesize", json={"person_id": pid, "text": "hello there"})
    assert r2.content == r.content


def test_synthesize_requires_person(client):
    c, pid = client
    r = c.post("/synthesize", json={"person_id": "person_missing", "text": "x"})
    assert r.status_code == 404


def test_synthesize_requires_text(client):
    c, pid = client
    r = c.post("/synthesize", json={"person_id": pid, "text": "   "})
    assert r.status_code == 400


def test_cache_is_fifo_and_memory_only(client):
    c, pid = client
    for i in range(70):  # over the 64-entry limit
        c.post("/synthesize", json={"person_id": pid, "text": f"line {i}"})
    assert len(tts_service._cache) <= 64
    # nothing written to disk
    assert not list(Path.home().joinpath("does-not-exist").glob("*"))
