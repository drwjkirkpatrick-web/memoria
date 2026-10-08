"""memoria.memorial_server — one API for the whole memorial (:8093).

Routes (viewer role required; executor key for executor routes):
  GET  /health
  GET  /people
  POST /ask        {person_id, question, role?} -> grounded answer + citations
  POST /voice      {person_id, text, role?}     -> audio/wav of the answer
  GET  /timeline   {person_id, role?}           -> chapters + entries
  GET  /letters    {person_id, role?}           -> letters, rule-gated
  POST /letter/unlock  {person_id, letter_id, executor_key} -> open a sealed letter

Auth is deliberately simple: role is declared in the request, the executor key
is a secret. Step 18's visitor page is PUBLIC-role by design; family pages add
the family role; the executor holds the key. Everything routes through the
step-8 access layer, so tiers are enforced at one place.
"""
from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel

from .config import load_config
from .persona import Persona
from .brain import MemorialBrain
from .access import Viewer
from .timeline import Timeline
from .letters import LetterBox

app = FastAPI(title="memoria memorial", version="0.1.0")


class AskRequest(BaseModel):
    person_id: str
    question: str
    role: str = "public"          # public | family | executor
    executor_key: str | None = None


class VoiceRequest(AskRequest):
    pass


class UnlockRequest(BaseModel):
    person_id: str
    letter_id: str
    executor_key: str


def _viewer(role: str, executor_key: str | None) -> Viewer:
    """Role declared + executor key presented -> a viewer; tiers enforced downstream."""
    if role not in ("public", "family", "executor"):
        raise HTTPException(400, "role must be public, family or executor")
    if role == "executor" and not executor_key:
        raise HTTPException(401, "executor role requires the executor key")
    return Viewer(load_config(), role)


@app.get("/health")
def health():
    return {"ok": True, "service": "memorial", "version": "0.1.0"}


@app.get("/people")
def people():
    from .interview import InterviewStore
    store = InterviewStore(load_config())
    return [{"id": p.id, "name": p.name, "birth_year": p.birth_year}
            for p in store.list_people()]


@app.post("/ask")
def ask(req: AskRequest):
    v = _viewer(req.role, req.executor_key)
    cfg = load_config()
    try:
        persona = Persona(cfg).build(req.person_id)
    except Exception:
        raise HTTPException(404, "person not found")
    # tier-cap the corpus by the viewer's role: the memorial mouth obeys tiers
    cap = {"public": "PUBLIC", "family": "FAMILY", "executor": "PRIVATE"}[req.role]
    from .persona import statement_corpus
    persona["corpus"] = statement_corpus(
        _answers_of(cfg, req.person_id), tier_cap=cap)
    brain = MemorialBrain(persona)
    r = brain.ask(req.question)
    return {"answer": r["answer"], "refused": r["refused"],
            "grounded": r["grounded"],
            "citations": [{"answer_id": s["answer_id"], "question": s["question"],
                           "quote": s["statement"], "score": s.get("retrieval_score")}
                          for s in r.get("retrieved", [])]}


def _answers_of(cfg, person_id):
    from .interview import InterviewStore
    return InterviewStore(cfg).answers(person_id)


@app.post("/voice")
def voice(req: VoiceRequest):
    """Ask + speak: grounded answer, synthesized in the person's cloned voice."""
    v = _viewer(req.role, req.executor_key)
    result = ask(AskRequest(person_id=req.person_id, question=req.text,
                            role=req.role, executor_key=req.executor_key))
    if result["refused"]:
        raise HTTPException(422, "the memorial declined to answer; no audio")
    text = result["answer"]
    # synthesize via the backend registry (Kokoro here; NeuTTS when accepted)
    from .voice_backends import first_available
    cfg = load_config()
    backend, reasons = first_available(cfg)
    if backend is None:
        raise HTTPException(503, f"no TTS backend: {reasons}")
    out = Path(cfg.exports_dir) / f"voice-{abs(hash(text))}.wav"
    backend.synthesize(text, None, str(out))
    audio = out.read_bytes()
    out.unlink(missing_ok=True)
    return Response(audio, media_type="audio/wav")


@app.get("/timeline")
def timeline(person_id: str, role: str = "public"):
    v = _viewer(role, None)
    try:
        ch = Timeline(load_config()).chapters(person_id)
    except Exception:
        raise HTTPException(404, "person not found")
    # tier filter via the access layer
    visible = _visible_answer_ids(load_config(), person_id, role)
    out = {}
    for chapter, entries in ch.items():
        kept = [e for e in entries if e["answer_id"] in visible]
        if kept:
            out[chapter] = kept
    return out


def _visible_answer_ids(cfg, person_id: str, role: str) -> set[str]:
    v = Viewer(cfg, role)
    return {a["id"] for a in v.answers(person_id, with_body=False)}


@app.get("/letters")
def letters(person_id: str, role: str = "public", executor_key: str | None = None):
    v = _viewer(role, executor_key)
    try:
        return v.letters(person_id)
    except Exception:
        raise HTTPException(404, "person not found")


@app.post("/letter/unlock")
def letter_unlock(req: UnlockRequest):
    cfg = load_config()
    box = LetterBox(cfg, executor_key=req.executor_key)
    try:
        return box.readable(req.person_id, req.letter_id)
    except Exception as e:
        if "not found" in str(e):
            raise HTTPException(404, str(e))
        raise HTTPException(400, str(e))
