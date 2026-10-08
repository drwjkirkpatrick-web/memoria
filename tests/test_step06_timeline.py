"""Step 6: timeline — chapters, keyword index, search with citations."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine
from memoria.timeline import Timeline, tokenize, keywords


def _person_with_life(tmp_path):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Ruth", 1942)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots", "joy", "work"])
    # engine walks in pack order (roots first): answer 6 of the 10 roots questions
    eng.answer("I grew up on a farm outside Salem with chickens and a barn.")
    eng.answer("We moved a lot because of my father's railroad work.")
    eng.answer("What were you afraid of as a child? Dogs, honestly.")
    eng.answer("The ocean at Cannon Beach, every summer, no matter what.")
    eng.answer("Best meal of my life was fried chicken at the state fair.")
    eng.answer("I was a nurse for forty years, mostly night shifts.")
    eng.pause()
    return store, p


def test_tokenize_and_keywords():
    assert tokenize("The chickens-and-peaches!") == ["the", "chickens", "and", "peaches"]
    assert "the" not in keywords("the farm outside salem")
    assert "farm" in keywords("the farm outside salem")


def test_timeline_builds_in_order(tmp_path):
    store, p = _person_with_life(tmp_path)
    tl = Timeline(MemoriaConfig(data_dir=str(tmp_path)))
    entries = tl.build(p.id)
    assert len(entries) == 6
    assert all(e.chapter == "roots" for e in entries)
    assert [e.index for e in entries] == [0, 1, 2, 3, 4, 5]


def test_chapters_grouping(tmp_path):
    store, p = _person_with_life(tmp_path)
    tl = Timeline(MemoriaConfig(data_dir=str(tmp_path)))
    ch = tl.chapters(p.id)
    assert set(ch) == {"roots"}
    assert len(ch["roots"]) == 6
    assert ch["roots"][-1]["text"].startswith("I was a nurse")


def test_search_finds_and_cites(tmp_path):
    store, p = _person_with_life(tmp_path)
    tl = Timeline(MemoriaConfig(data_dir=str(tmp_path)))

    hits = tl.search(p.id, "chickens on the farm")
    assert len(hits) >= 1
    top = hits[0]
    assert "chickens" in top["match_words"]
    assert "farm" in top["text"]
    # full citation back to the exact answer
    cit = top["citation"]
    assert cit["answer_id"].startswith("ans_")
    assert cit["question_text"].startswith("Where did you grow up")
    assert cit["quote"] == top["text"]
    # citations resolve: the answer id exists in the store
    assert any(a.id == cit["answer_id"] for a in store.answers(p.id))


def test_search_ranks_multiword_higher(tmp_path):
    store, p = _person_with_life(tmp_path)
    tl = Timeline(MemoriaConfig(data_dir=str(tmp_path)))
    hits = tl.search(p.id, "chickens barn farm salem")
    assert hits[0]["score"] >= 2
    assert hits[0]["score"] >= hits[-1]["score"]


def test_search_no_match_returns_empty(tmp_path):
    store, p = _person_with_life(tmp_path)
    tl = Timeline(MemoriaConfig(data_dir=str(tmp_path)))
    assert tl.search(p.id, "quantum computing") == []
    assert tl.search(p.id, "") == []


def test_top_keywords_sketch(tmp_path):
    store, p = _person_with_life(tmp_path)
    tl = Timeline(MemoriaConfig(data_dir=str(tmp_path)))
    top = tl.top_keywords(p.id, limit=5)
    assert len(top) == 5
    words = [w for w, _ in top]
    assert "chickens" in words or "farm" in words or "salem" in words


def test_search_limit_respected(tmp_path):
    store, p = _person_with_life(tmp_path)
    tl = Timeline(MemoriaConfig(data_dir=str(tmp_path)))
    hits = tl.search(p.id, "my work farm chickens barn railroad", limit=2)
    assert len(hits) <= 2
