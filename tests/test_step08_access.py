"""Step 8: consent tiers — who may see what, enforced in every path."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine
from memoria.access import Viewer, allowed, visible_tiers, AccessError
from memoria.letters import LetterBox


def _archive_with_tiers(tmp_path):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Ruth", 1942)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots"])
    eng.answer("I grew up on a farm outside Salem.", tier="PUBLIC")
    eng.answer("My mother sang while she cooked.", tier="FAMILY")
    eng.answer("I was afraid of the dark until I was twelve.", tier="PRIVATE")
    eng.pause()
    # letters in each tier
    box = LetterBox(MemoriaConfig(data_dir=str(tmp_path)))
    box.write(p.id, "the world", "Thank you for visiting.", tier="PUBLIC",
              open_rule="on-date", open_date="2020-01-01")
    box.write(p.id, "my children", "The bank box key is under the porch.", tier="FAMILY")
    box.write(p.id, "my daughter", "What I never told you about your father.", tier="PRIVATE")
    return store, p


def test_allowed_matrix():
    assert allowed("public", "PUBLIC")
    assert not allowed("public", "FAMILY")
    assert not allowed("public", "PRIVATE")
    assert allowed("family", "FAMILY")
    assert not allowed("family", "PRIVATE")
    assert allowed("executor", "PRIVATE")


def test_visible_tiers():
    assert visible_tiers("public") == ("PUBLIC",)
    assert visible_tiers("family") == ("PUBLIC", "FAMILY")
    assert visible_tiers("executor") == ("PUBLIC", "FAMILY", "PRIVATE")


def test_unknown_role_rejected():
    with pytest.raises(AccessError):
        allowed("stranger", "PUBLIC")
    with pytest.raises(AccessError):
        Viewer(MemoriaConfig(data_dir="/tmp/x"), "stranger")


def test_public_viewer_sees_only_public_answers(tmp_path):
    store, p = _archive_with_tiers(tmp_path)
    v = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "public")
    answers = v.answers(p.id)
    assert len(answers) == 1
    assert answers[0]["text"].startswith("I grew up on a farm")
    # summary shows counts but not private content
    s = v.summary(p.id)
    assert s["total"] == 3 and s["visible"] == 1


def test_family_viewer_sees_public_and_family(tmp_path):
    store, p = _archive_with_tiers(tmp_path)
    v = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "family")
    answers = v.answers(p.id)
    assert len(answers) == 2
    texts = {a["text"] for a in answers}
    assert any("sang" in t for t in texts)
    assert not any("afraid of the dark" in t for t in texts)


def test_executor_sees_all(tmp_path):
    store, p = _archive_with_tiers(tmp_path)
    v = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "executor")
    answers = v.answers(p.id)
    assert len(answers) == 3
    assert v.summary(p.id)["visible"] == 3


def test_tier_filtered_search(tmp_path):
    store, p = _archive_with_tiers(tmp_path)
    v = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "public")
    hits = v.search(p.id, "farm salem")
    assert len(hits) == 1 and hits[0]["text"].startswith("I grew up")
    # a public viewer searching for private content gets nothing
    assert v.search(p.id, "afraid dark") == []
    # family cannot see PRIVATE answers — that tier is executor-only
    vf = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "family")
    assert vf.search(p.id, "afraid dark") == []
    # executor finds it
    ve = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "executor")
    assert len(ve.search(p.id, "afraid dark")) == 1


def test_letter_tiers_gated(tmp_path):
    store, p = _archive_with_tiers(tmp_path)
    # public: only the PUBLIC letter, and it is already open (past date)
    vp = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "public")
    lp = vp.letters(p.id)
    assert len(lp) == 1 and lp[0]["sealed"] is False
    # family: PUBLIC + FAMILY(executor-sealed for them)
    vf = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "family")
    lf = vf.letters(p.id)
    assert len(lf) == 2
    sealed_ids = [l["id"] for l in lf if l["sealed"]]
    assert len(sealed_ids) == 1  # the FAMILY executor letter is sealed to family viewers
    assert all("body" not in l for l in lf if l["sealed"])
    # executor: all three
    ve = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "executor")
    le = ve.letters(p.id)
    assert len(le) == 3


def test_delete_person_executor_only(tmp_path):
    store, p = _archive_with_tiers(tmp_path)
    v = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "family")
    with pytest.raises(AccessError):
        v.delete_person(p.id)
    ve = Viewer(MemoriaConfig(data_dir=str(tmp_path)), "executor")
    ve.delete_person(p.id)
    assert not Path(store.person_dir(p.id)).exists()
    with pytest.raises(Exception):
        store.get_person(p.id)  # gone
