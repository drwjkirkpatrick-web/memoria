"""Step 3: interview engine lifecycle — start, answer, skip, pause, resume, complete."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine, InterviewError


@pytest.fixture
def store(tmp_path):
    return InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))


def test_person_crud(store):
    p = store.create_person("Walker", 1979)
    assert store.get_person(p.id).name == "Walker"
    assert store.get_person(p.id).birth_year == 1979
    assert len(store.list_people()) == 1
    with pytest.raises(InterviewError):
        store.get_person("person_missing")


def test_session_full_lifecycle(store):
    p = store.create_person("Ada")
    eng = InterviewEngine(store, p.id)
    sess = eng.start("starter", chapters=["roots"])   # 10 questions
    assert len(sess.question_ids) == 10

    # answer one
    q1 = eng.current_question
    a1 = eng.answer("By the sea.")
    assert a1.question_id == q1.id
    assert store.answers(p.id)[0].text == "By the sea."
    assert eng.progress == (1, 10)

    # skip one
    q2 = eng.current_question
    skipped_id = eng.skip()
    assert skipped_id == q2.id
    assert eng.progress == (1, 10)

    # answer the rest
    n = 0
    while eng.current_question is not None:
        eng.answer(f"answer {n}")
        n += 1
    assert (len(eng.session.answered), len(eng.session.skipped)) == (9, 1)

    # complete
    s = eng.complete()
    assert s.status == "complete"
    assert eng.summary()["answered"] == 9


def test_answers_persist_immediately(store):
    """An interrupted session never loses a word."""
    p = store.create_person("Ada")
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots"])
    eng.answer("first words")
    # crash simulation: a brand new engine sees the answer on disk
    eng2 = InterviewEngine(store, p.id)
    assert len(store.answers(p.id)) == 1
    assert store.answers(p.id)[0].text == "first words"


def test_pause_resume_roundtrip(store):
    p = store.create_person("Ada")
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["growing"])
    eng.answer("a1")
    eng.pause()
    assert eng.session.status == "paused"

    # a fresh engine resumes from disk
    eng2 = InterviewEngine(store, p.id)
    sess = store.latest_session(p.id)
    assert sess.status == "paused"
    eng2.resume(sess.id)
    assert eng2.session.status == "active"
    # pending is rebuilt: 9 questions remain
    answered, total = eng2.progress
    assert (answered, total) == (1, 10)
    # the first pending question is the unanswered one
    assert eng2.current_question is not None
    assert eng2.current_question.id not in eng2.session.answered


def test_skip_is_persisted(store):
    p = store.create_person("Ada")
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["joy"])
    eng.skip()
    eng.skip()
    eng.pause()
    eng2 = InterviewEngine(store, p.id)
    eng2.resume(store.latest_session(p.id).id)
    assert len(eng2.session.skipped) == 2
    assert eng2.current_question is not None
    # the skipped questions never come back
    assert eng2.current_question.id not in eng2.session.skipped


def test_state_machine_guards(store):
    p = store.create_person("Ada")
    eng = InterviewEngine(store, p.id)
    with pytest.raises(InterviewError):
        eng.answer("no session")
    eng.start("starter", chapters=["roots"])
    with pytest.raises(InterviewError):
        eng.start("starter")  # already active
    eng.pause()
    with pytest.raises(InterviewError):
        eng.answer("paused")  # must resume first
    eng.resume(eng.session.id)
    eng.answer("ok")
    eng.complete()
    with pytest.raises(InterviewError):
        eng.answer("after complete")


def test_empty_answer_rejected(store):
    p = store.create_person("Ada")
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots"])
    with pytest.raises(InterviewError):
        eng.answer("   ")


def test_chapter_selection(store):
    p = store.create_person("Ada")
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots", "love"])
    assert len(eng.session.question_ids) == 20
    chapters = {q.chapter for q in _walk(eng)}
    assert chapters <= {"roots", "love"}


def _walk(eng):
    """Pop every remaining question without answering."""
    qs = []
    while eng.current_question is not None:
        qs.append(eng.current_question)
        eng.skip()
    return qs
