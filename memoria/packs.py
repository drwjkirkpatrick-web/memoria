"""memoria.packs — interview question packs.

Packs are YAML files in memoria/packs/ (built-in) plus MEMORIA_DATA/packs/
(own questions). Malformed packs are rejected loudly, never silently loaded.
"""
from __future__ import annotations
import os
from pathlib import Path

import yaml

from .models import Question

BUILTIN_PACKS_DIR = Path(__file__).parent / "packs"


class PackError(Exception):
    """A pack file is malformed. Fail loudly so no question is lost silently."""


def _validate_question(d: dict, pack: str, where: str) -> dict:
    if not isinstance(d, dict):
        raise PackError(f"{where}: question must be a mapping, got {type(d).__name__}")
    text = d.get("text")
    if not isinstance(text, str) or not text.strip():
        raise PackError(f"{where}: question text missing or empty")
    follow_ups = d.get("follow_ups", [])
    if not isinstance(follow_ups, list) or any(not isinstance(f, str) or not f.strip()
                                               for f in follow_ups):
        raise PackError(f"{where}: follow_ups must be a list of non-empty strings")
    tier = d.get("tier", "PRIVATE")
    if tier not in ("PUBLIC", "FAMILY", "PRIVATE"):
        raise PackError(f"{where}: unknown tier {tier!r}")
    return {"text": text.strip(), "follow_ups": [f.strip() for f in follow_ups],
            "tier": tier, "chapter": None}  # chapter filled by caller


def _load_pack_file(path: Path) -> dict:
    where = str(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PackError(f"{where}: YAML parse error: {e}")
    if not isinstance(raw, dict):
        raise PackError(f"{where}: pack must be a mapping at top level")
    for key in ("pack", "name", "chapters"):
        if key not in raw:
            raise PackError(f"{where}: missing required key {key!r}")
    chapters = raw["chapters"]
    if not isinstance(chapters, list) or not chapters:
        raise PackError(f"{where}: chapters must be a non-empty list")
    pack_id = raw["pack"]
    if not isinstance(pack_id, str) or not pack_id.strip():
        raise PackError(f"{where}: pack id must be a non-empty string")

    questions: list[Question] = []
    seen_qids: set[str] = set()
    for ch in chapters:
        ch_where = f"{where}: chapter"
        if not isinstance(ch, dict) or "id" not in ch or "title" not in ch:
            raise PackError(f"{ch_where}: each chapter needs id and title")
        if not isinstance(ch["questions"], list) or not ch["questions"]:
            raise PackError(f"{ch_where} {ch['id']!r}: questions must be a non-empty list")
        for qd in ch["questions"]:
            spec = _validate_question(qd, pack_id, ch_where)
            q = Question(id=f"q_{pack_id}_{ch['id']}_{len(questions)+1}",
                         chapter=ch["id"], text=spec["text"],
                         follow_ups=spec["follow_ups"], tier=spec["tier"])
            if q.id in seen_qids:
                raise PackError(f"{where}: duplicate question id {q.id}")
            seen_qids.add(q.id)
            questions.append(q)
    if not questions:
        raise PackError(f"{where}: pack has no questions")
    return {"pack": pack_id, "name": raw["name"],
            "description": raw.get("description", ""), "questions": questions}


def load_pack(pack_id: str, data_dir: str | None = None) -> dict:
    """Load one pack by id. Own packs (data dir) shadow built-in packs by id."""
    candidates = []
    if data_dir:
        candidates.append(Path(data_dir) / "packs" / f"{pack_id}.yaml")
    candidates.append(BUILTIN_PACKS_DIR / f"{pack_id}.yaml")
    for path in candidates:
        if path.is_file():
            return _load_pack_file(path)
    raise PackError(f"pack not found: {pack_id!r} (looked in {[str(c) for c in candidates]})")


def list_packs(data_dir: str | None = None) -> list[dict]:
    """Available packs: [{id, name, questions, source}] — own packs shadow built-ins."""
    found: dict[str, dict] = {}
    for source, d in (("builtin", BUILTIN_PACKS_DIR),):
        for p in sorted(d.glob("*.yaml")):
            try:
                pack = _load_pack_file(p)
            except PackError:
                continue
            found[pack["pack"]] = {"id": pack["pack"], "name": pack["name"],
                                   "questions": len(pack["questions"]), "source": source}
    if data_dir:
        own = Path(data_dir) / "packs"
        if own.is_dir():
            for p in sorted(own.glob("*.yaml")):
                try:
                    pack = _load_pack_file(p)
                except PackError:
                    continue
                found[pack["pack"]] = {"id": pack["pack"], "name": pack["name"],
                                       "questions": len(pack["questions"]), "source": "own"}
    return list(found.values())


def custom_question(text: str, chapter: str = "custom",
                    follow_ups: list[str] | None = None) -> Question:
    """A one-off question written by hand."""
    import uuid
    if not text or not text.strip():
        raise ValueError("question text is required")
    return Question(id=f"q_custom_{uuid.uuid4().hex[:8]}", chapter=chapter,
                    text=text.strip(), follow_ups=follow_ups or [])
