"""memoria.interview — the guided interview engine.

A session walks a person through a pack: start, ask, record an answer, skip,
pause, resume. Every answer is persisted the moment it is given, so an
interrupted session never loses a word.
"""
from __future__ import annotations
import os
import uuid
from pathlib import Path

from .config import MemoriaConfig
from .models import Answer, InterviewSession, Person, Question, to_json_line, from_json_line
from .packs import load_pack, custom_question


class InterviewError(Exception):
    """Interview state machine violated."""


class InterviewStore:
    """Filesystem store for one person's records, under the data dir."""

    def __init__(self, config: MemoriaConfig):
        self.config = config
        self.config.ensure_dirs()

    # -- paths -------------------------------------------------------------
    def person_dir(self, person_id: str) -> Path:
        return Path(self.config.person_dir(person_id))

    def _records_path(self, person_id: str) -> Path:
        return self.person_dir(person_id) / "records.jsonl"

    # -- people ------------------------------------------------------------
    def create_person(self, name: str, birth_year: int | None = None) -> Person:
        person = Person.create(name, birth_year)
        d = self.person_dir(person.id)
        d.mkdir(parents=True, exist_ok=True)
        atomic_write(d / "person.json", to_json_line(person).encode())
        return person

    def get_person(self, person_id: str) -> Person:
        p = self.person_dir(person_id) / "person.json"
        if not p.is_file():
            raise InterviewError(f"person not found: {person_id}")
        return from_json_line(p.read_text(encoding="utf-8"))

    def list_people(self) -> list[Person]:
        root = Path(self.config.people_dir)
        out = []
        if root.is_dir():
            for d in sorted(root.iterdir()):
                pj = d / "person.json"
                if pj.is_file():
                    out.append(from_json_line(pj.read_text(encoding="utf-8")))
        return out

    # -- append-only records -------------------------------------------------
    def _append(self, person_id: str, record) -> None:
        line = (to_json_line(record) + "\n").encode("utf-8")
        path = self._records_path(person_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def add_answer(self, answer: Answer) -> None:
        self._append(answer.person_id, answer)

    def add_letter(self, letter) -> None:
        self._append(letter.person_id, letter)

    def add_voice_sample(self, sample) -> None:
        self._append(sample.person_id, sample)

    def add_session(self, session: InterviewSession) -> None:
        self._append(session.person_id, session)

    def _all_records(self, person_id: str) -> list:
        path = self._records_path(person_id)
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(from_json_line(line))
        return out

    def answers(self, person_id: str) -> list[Answer]:
        return [r for r in self._all_records(person_id) if isinstance(r, Answer)]

    def letters(self, person_id: str) -> list:
        return [r for r in self._all_records(person_id)
                if type(r).__name__ == "Letter"]

    def sessions(self, person_id: str) -> list[InterviewSession]:
        return [r for r in self._all_records(person_id) if isinstance(r, InterviewSession)]

    def voice_samples(self, person_id: str) -> list:
        return [r for r in self._all_records(person_id)
                if type(r).__name__ == "VoiceSample"]

    def latest_session(self, person_id: str) -> InterviewSession | None:
        sess = self.sessions(person_id)
        return sess[-1] if sess else None


from .storage import atomic_write


class InterviewEngine:
    """Drives one session through a list of questions, persisting as it goes."""

    def __init__(self, store: InterviewStore, person_id: str):
        self.store = store
        self.person_id = person_id
        self.session: InterviewSession | None = None
        self._pending: list[Question] = []

    # -- lifecycle -----------------------------------------------------------
    def start(self, pack_id: str, chapters: list[str] | None = None,
              data_dir: str | None = None) -> InterviewSession:
        if self.session is not None and self.session.status == "active":
            raise InterviewError("a session is already active — pause or complete it first")
        pack = load_pack(pack_id, data_dir=data_dir or self.store.config.data_dir)
        qs = pack["questions"]
        if chapters:
            wanted = set(chapters)
            qs = [q for q in qs if q.chapter in wanted]
            if not qs:
                raise InterviewError(f"no questions in chapters {chapters}")
        self.session = InterviewSession(id=f"sess_{uuid.uuid4().hex[:10]}",
                                        person_id=self.person_id,
                                        question_ids=[q.id for q in qs])
        self._pending = list(qs)
        self.store.add_session(self.session)
        return self.session

    def resume(self, session_id: str) -> InterviewSession:
        """Resume a paused (or interrupted) session by id — rebuild pending list."""
        if self.session is not None and self.session.status == "active":
            raise InterviewError("a session is already active — pause or complete it first")
        sess = None
        for s in self.store.sessions(self.person_id):
            if s.id == session_id:
                sess = s
        if sess is None:
            raise InterviewError(f"session not found: {session_id}")
        if sess.status == "complete":
            raise InterviewError("session is complete — start a new one")
        self.session = sess
        # Rebuild pending: all pack questions not yet answered or skipped.
        # The pack is reloadable from the session's question ids via the starter pack.
        answered = set(sess.answered)
        skipped = set(sess.skipped)
        all_questions = {q.id: q for q in self._questions_for_session(sess)}
        self._pending = [all_questions[qid] for qid in sess.question_ids
                         if qid not in answered and qid not in skipped
                         and qid in all_questions]
        sess.status = "active"
        self.store.add_session(sess)
        return sess

    def _questions_for_session(self, sess: InterviewSession) -> list[Question]:
        """Reload the pack questions a session was built from."""
        # Question ids look like q_<pack>_<chapter>_<n> — recover pack from first id.
        if not sess.question_ids:
            return []
        first = sess.question_ids[0]
        parts = first.split("_")
        if len(parts) >= 4 and parts[0] == "q":
            pack_id = parts[1]
            try:
                pack = load_pack(pack_id, data_dir=self.store.config.data_dir)
                return pack["questions"]
            except Exception:
                return []
        # custom questions cannot be reloaded from a pack — build minimal stubs
        return [Question(id=qid, chapter="custom", text="(question text unavailable)")
                for qid in sess.question_ids]

    def _require_active(self) -> InterviewSession:
        if self.session is None:
            raise InterviewError("no session — call start() first")
        if self.session.status != "active":
            raise InterviewError(f"session is {self.session.status} — resume() first")
        return self.session

    # -- stepping ------------------------------------------------------------
    @property
    def current_question(self) -> Question | None:
        if self.session is None or self.session.status != "active" or not self._pending:
            return None
        return self._pending[0]

    @property
    def progress(self) -> tuple[int, int]:
        """(answered, total) for the active session."""
        if self.session is None:
            return (0, 0)
        total = len(self.session.question_ids)
        return (len(self.session.answered), total)

    def answer(self, text: str, tier: str = "PRIVATE") -> Answer:
        sess = self._require_active()
        if not self._pending:
            raise InterviewError("no question pending — session is finished")
        q = self._pending[0]
        if not text or not text.strip():
            raise InterviewError("answer text is required — or skip()")
        ans = Answer(id=f"ans_{uuid.uuid4().hex[:12]}", person_id=self.person_id,
                     question_id=q.id, question_text=q.text, text=text.strip(),
                     tier=tier, session_id=sess.id)
        self.store.add_answer(ans)
        sess.answered[q.id] = ans.id
        self._pending.pop(0)
        self._autosave()
        return ans

    def skip(self) -> str:
        """Skip the current question; returns its id."""
        sess = self._require_active()
        if not self._pending:
            raise InterviewError("nothing to skip")
        q = self._pending.pop(0)
        sess.skipped.append(q.id)
        self._autosave()
        return q.id

    def pause(self) -> None:
        if self.session is None:
            raise InterviewError("no session")
        if self.session.status == "active":
            self.session.status = "paused"
            self._autosave()

    def complete(self) -> InterviewSession:
        sess = self._require_active()
        sess.complete()
        self._autosave()
        return sess

    def summary(self) -> dict:
        """Completion summary for a session (active or finished)."""
        if self.session is None:
            raise InterviewError("no session")
        s = self.session
        return {"session_id": s.id, "status": s.status,
                "answered": len(s.answered), "skipped": len(s.skipped),
                "total": len(s.question_ids)}

    def _autosave(self) -> None:
        """Sessions are append-only; the latest record reflects current state."""
        self.store.add_session(self.session)
