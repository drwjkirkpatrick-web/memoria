"""memoria.access — who may see what.

Every answer and letter carries a tier: PUBLIC, FAMILY, PRIVATE.
Every viewer has a role: public, family, executor.

    viewer \ content    PUBLIC   FAMILY   PRIVATE
    public               yes       no        no
    family               yes       yes       no
    executor             yes       yes       yes

Exports and API responses must filter through this module — a viewer never
receives content above their tier. This is the project's second invariant,
enforced in code, not by convention.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .config import MemoriaConfig
from .interview import InterviewStore

TIERS = ("PUBLIC", "FAMILY", "PRIVATE")
_TIER_RANK = {"PUBLIC": 0, "FAMILY": 1, "PRIVATE": 2}
_ROLE_MAX_TIER = {"public": 0, "family": 1, "executor": 2}


class AccessError(Exception):
    pass


def allowed(role: str, tier: str) -> bool:
    """May a viewer with `role` see content marked `tier`?"""
    if role not in _ROLE_MAX_TIER:
        raise AccessError(f"unknown role: {role!r}")
    if tier not in _TIER_RANK:
        raise AccessError(f"unknown tier: {tier!r}")
    return _TIER_RANK[tier] <= _ROLE_MAX_TIER[role]


def visible_tiers(role: str) -> tuple[str, ...]:
    if role not in _ROLE_MAX_TIER:
        raise AccessError(f"unknown role: {role!r}")
    return tuple(t for t in TIERS if _TIER_RANK[t] <= _ROLE_MAX_TIER[role])


class Viewer:
    """One viewer's lens over the archive."""

    def __init__(self, config: MemoriaConfig, role: str):
        if role not in _ROLE_MAX_TIER:
            raise AccessError(f"unknown role: {role!r}")
        self.config = config
        self.role = role
        self.store = InterviewStore(config)

    def _filter_answer(self, a, with_body: bool):
        if not allowed(self.role, a.tier):
            return None
        d = {"id": a.id, "question_id": a.question_id, "question_text": a.question_text,
             "tier": a.tier, "answered_at": a.answered_at, "chapter": None}
        if with_body:
            d["text"] = a.text
        return d

    def answers(self, person_id: str, with_body: bool = True) -> list[dict]:
        person = self.store.get_person(person_id)
        out = []
        for a in self.store.answers(person_id):
            d = self._filter_answer(a, with_body)
            if d is not None:
                out.append(d)
        return out

    def letters(self, person_id: str) -> list[dict]:
        """Letters through the viewer's lens: tier-filtered and rule-gated."""
        from .letters import LetterBox
        box = LetterBox(self.config, executor_key="executor" if self.role == "executor" else None)
        out = []
        for l in self.store.letters(person_id):
            if not allowed(self.role, l.tier):
                continue
            d = box.readable(person_id, l.id)
            out.append(d)
        return out

    def search(self, person_id: str, query: str, limit: int = 10) -> list[dict]:
        """Tier-filtered search: PRIVATE answers invisible to the public."""
        from .timeline import Timeline
        hits = Timeline(self.config).search(person_id, query, limit=limit)
        out = []
        for h in hits:
            if not allowed(self.role, h.get("tier", "PRIVATE")):
                continue
            out.append(h)
        return out

    # -- person-level operations ----------------------------------------------
    def delete_person(self, person_id: str) -> int:
        """Executor-only: remove a person and everything about them. Returns files removed."""
        if self.role != "executor":
            raise AccessError("only the executor may delete a person")
        pdir = Path(self.config.person_dir(person_id))
        n = 0
        if pdir.is_dir():
            import shutil
            shutil.rmtree(pdir)
            n = 1
        # remove exports too
        exports = Path(self.config.exports_dir)
        if exports.is_dir():
            for f in exports.glob(f"{person_id}*"):
                f.unlink()
                n += 1
        return n

    def summary(self, person_id: str) -> dict:
        """Counts by tier, respecting the viewer's own role (no content leak)."""
        person = self.store.get_person(person_id)
        all_answers = self.store.answers(person_id)
        counts = {"total": len(all_answers), "visible": 0, "by_tier": {"PUBLIC": 0, "FAMILY": 0, "PRIVATE": 0}}
        for a in all_answers:
            counts["by_tier"][a.tier] = counts["by_tier"].get(a.tier, 0) + 1
            if allowed(self.role, a.tier):
                counts["visible"] += 1
        return counts
