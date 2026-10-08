"""memoria.letters — sealed messages to the future.

A legacy letter is written by the person while they are alive and sealed until
a rule is satisfied:

- `executor`: opened only when the estate executor explicitly approves.
- `on-date`: opens automatically on a calendar date.

The sealed body is never included in exports or API responses until the rule
is satisfied. This is a human gate, and the code enforces it.
"""
from __future__ import annotations
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from .config import MemoriaConfig
from .interview import InterviewStore
from .models import Letter


class LetterError(Exception):
    pass


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


class LetterBox:
    """All letters for one person, with unlock-rule enforcement."""

    def __init__(self, config: MemoriaConfig, executor_key: str | None = None):
        self.config = config
        self.store = InterviewStore(config)
        # The executor key stands in for real auth (step 17 wires the API layer);
        # tests inject it to prove the gate works both ways.
        self.executor_key = executor_key

    def _require_person(self, person_id: str) -> None:
        self.store.get_person(person_id)  # raises InterviewError if unknown

    def write(self, person_id: str, recipient: str, body: str,
              occasion: str = "", open_rule: str = "executor",
              open_date: str | None = None, tier: str = "PRIVATE") -> Letter:
        """The person writes a sealed letter (in life)."""
        self._require_person(person_id)
        if not body or not body.strip():
            raise LetterError("letter body is required")
        if not recipient or not recipient.strip():
            raise LetterError("recipient is required")
        letter = Letter(id=f"ltr_{uuid.uuid4().hex[:12]}",
                        person_id=person_id, recipient=recipient.strip(),
                        occasion=occasion.strip(), body=body.strip(),
                        open_rule=open_rule, open_date=open_date, tier=tier)
        self.store.add_letter(letter)
        return letter

    # -- unlock logic ---------------------------------------------------------
    def _rule_satisfied(self, letter: Letter, today: date) -> bool:
        if letter.open_rule == "on-date":
            return letter.open_date is not None and date.fromisoformat(letter.open_date) <= today
        return False  # executor letters never auto-open

    def _is_executor(self) -> bool:
        return bool(self.executor_key)

    def _unlock_log(self, person_id: str, letter_id: str, by: str, rule: str) -> None:
        entry = {"letter_id": letter_id, "by": by, "rule": rule,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        pdir = Path(self.config.person_dir(person_id))
        pdir.mkdir(parents=True, exist_ok=True)
        with open(pdir / "unlocks.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def readable(self, person_id: str, letter_id: str) -> dict:
        """Read one letter IF its rule is satisfied (or the executor opens it).
        Sealed letters return metadata only — never the body."""
        self._require_person(person_id)
        letter = self._find(person_id, letter_id)
        today = _today_utc()
        if self._rule_satisfied(letter, today):
            self._unlock_log(person_id, letter_id, by="date-rule", rule=letter.open_rule)
            return self._full(letter, sealed=False)
        if letter.open_rule == "executor" and self._is_executor():
            self._unlock_log(person_id, letter_id, by="executor", rule=letter.open_rule)
            return self._full(letter, sealed=False)
        return self._stub(letter)

    def readable_all(self, person_id: str) -> list[dict]:
        """All letters, each sealed or open according to its rule."""
        self._require_person(person_id)
        return [self.readable(person_id, l.id) for l in self.store.letters(person_id)]

    def _find(self, person_id: str, letter_id: str) -> Letter:
        for l in self.store.letters(person_id):
            if l.id == letter_id:
                return l
        raise LetterError(f"letter not found: {letter_id}")

    def _full(self, letter: Letter, sealed: bool) -> dict:
        return {"id": letter.id, "person_id": letter.person_id,
                "recipient": letter.recipient, "occasion": letter.occasion,
                "body": letter.body, "open_rule": letter.open_rule,
                "rule_satisfied": not sealed, "sealed": sealed,
                "open_date": letter.open_date, "tier": letter.tier,
                "created_at": letter.created_at}

    def _stub(self, letter: Letter) -> dict:
        return {"id": letter.id, "person_id": letter.person_id,
                "recipient": letter.recipient, "occasion": letter.occasion,
                "open_rule": letter.open_rule, "rule_satisfied": False,
                "sealed": True, "open_date": letter.open_date,
                "tier": letter.tier, "created_at": letter.created_at}
