"""memoria.models — the core records of a life.

Everything that persists is a dataclass with an id and timestamps, serialized
as JSON. Answer ids are stable forever: citations and letters point at them.
"""
from __future__ import annotations
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


TIERS = ("PUBLIC", "FAMILY", "PRIVATE")
_TIER_RANK = {t: i for i, t in enumerate(TIERS)}


def tier_rank(tier: str) -> int:
    if tier not in _TIER_RANK:
        raise ValueError(f"unknown tier: {tier!r}")
    return _TIER_RANK[tier]


@dataclass
class Person:
    """A person whose memoria this is."""
    id: str
    name: str
    birth_year: int | None = None
    created_at: str = field(default_factory=_now)
    notes: str = ""

    @staticmethod
    def create(name: str, birth_year: int | None = None) -> "Person":
        if not name or not name.strip():
            raise ValueError("name is required")
        return Person(id=_new_id("person"), name=name.strip(), birth_year=birth_year)


@dataclass
class Question:
    """One interview question, from a pack or written by hand."""
    id: str
    chapter: str
    text: str
    follow_ups: list[str] = field(default_factory=list)
    tier: str = "PRIVATE"

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier: {self.tier!r}")
        if not self.text or not self.text.strip():
            raise ValueError("question text is required")


@dataclass
class Answer:
    """A person's own words, in answer to a Question. The atom of the archive."""
    id: str
    person_id: str
    question_id: str
    question_text: str
    text: str
    answered_at: str = field(default_factory=_now)
    tier: str = "PRIVATE"
    transcript_ref: str | None = None   # path to a transcript/audio, if any
    session_id: str | None = None

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier: {self.tier!r}")
        if not self.text or not self.text.strip():
            raise ValueError("answer text is required")


@dataclass
class InterviewSession:
    """One sitting: which questions were asked, which answered or skipped."""
    id: str
    person_id: str
    started_at: str = field(default_factory=_now)
    completed_at: str | None = None
    question_ids: list[str] = field(default_factory=list)
    answered: dict[str, str] = field(default_factory=dict)   # question_id -> answer_id
    skipped: list[str] = field(default_factory=list)
    status: str = "active"  # active | paused | complete

    def complete(self):
        self.completed_at = _now()
        self.status = "complete"


@dataclass
class Letter:
    """A sealed message from the person, to be opened by a rule."""
    id: str
    person_id: str
    recipient: str
    occasion: str = ""
    body: str = ""
    open_rule: str = "executor"        # executor | on-date
    open_date: str | None = None       # ISO date, required when open_rule == on-date
    tier: str = "PRIVATE"
    created_at: str = field(default_factory=_now)
    opened_at: str | None = None

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier: {self.tier!r}")
        if self.open_rule not in ("executor", "on-date"):
            raise ValueError(f"open_rule must be executor or on-date, got {self.open_rule!r}")
        if self.open_rule == "on-date" and not self.open_date:
            raise ValueError("on-date letters require open_date")


@dataclass
class VoiceSample:
    """A recorded clip of the person's voice."""
    id: str
    person_id: str
    path: str
    duration_s: float = 0.0
    recorded_at: str = field(default_factory=_now)
    quality_report: dict = field(default_factory=dict)


def to_json(obj) -> str:
    """Serialize a record dataclass to a JSON line."""
    return json.dumps(asdict(obj), ensure_ascii=False)


def from_json_line(line: str):
    """Rebuild the right record from a JSON line."""
    d = json.loads(line)
    kind = d.pop("_kind", None)
    if kind == "person":
        return Person(**d)
    if kind == "answer":
        return Answer(**d)
    if kind == "question":
        return Question(**d)
    if kind == "session":
        return InterviewSession(**d)
    if kind == "letter":
        return Letter(**d)
    if kind == "voice_sample":
        return VoiceSample(**d)
    raise ValueError(f"unknown record kind: {kind!r}")


_KIND_TAG = {Person: "person", Question: "question", Answer: "answer",
             InterviewSession: "session", Letter: "letter", VoiceSample: "voice_sample"}


def to_json_line(obj) -> str:
    """Serialize with a _kind tag so from_json_line can rebuild it."""
    d = asdict(obj)
    try:
        d["_kind"] = _KIND_TAG[type(obj)]
    except KeyError:
        raise ValueError(f"cannot serialize record of type {type(obj).__name__}")
    # canonical key order: _kind first for readability
    ordered = {"_kind": d.pop("_kind")}
    ordered.update(d)
    return json.dumps(ordered, ensure_ascii=False)
