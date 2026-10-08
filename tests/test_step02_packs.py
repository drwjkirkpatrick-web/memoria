"""Step 2: question packs load, validate, and reject malformed files."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.packs import (PackError, load_pack, list_packs, custom_question,
                           BUILTIN_PACKS_DIR)


def test_starter_pack_loads():
    pack = load_pack("starter")
    assert pack["pack"] == "starter"
    assert pack["name"]
    qs = pack["questions"]
    assert len(qs) == 80, f"expected 80 starter questions, got {len(qs)}"
    # 8 chapters, 10 each
    chapters = {}
    for q in qs:
        chapters.setdefault(q.chapter, []).append(q)
    assert len(chapters) == 8
    assert all(len(v) == 10 for v in chapters.values())
    assert set(chapters) == {"roots", "growing", "love", "work",
                            "wisdom", "regrets", "joy", "farewells"}
    # every question has a stable unique id and real text
    ids = [q.id for q in qs]
    assert len(set(ids)) == 80
    assert all(q.text.strip() for q in qs)


def test_follow_ups_present_on_some():
    pack = load_pack("starter")
    with_fu = [q for q in pack["questions"] if q.follow_ups]
    assert 5 <= len(with_fu) <= 80
    assert all(isinstance(f, str) and f.strip()
               for q in with_fu for f in q.follow_ups)


def test_malformed_pack_rejected(tmp_path):
    def expect_error(content: str, name="bad.yaml"):
        p = tmp_path / "packs"
        p.mkdir(exist_ok=True)
        f = p / name
        f.write_text(content, encoding="utf-8")
        with pytest.raises(PackError):
            load_pack(name.replace(".yaml", ""), data_dir=str(tmp_path))

    expect_error("not: a: mapping\n")                       # not a mapping
    expect_error("pack: x\nname: X\n")                    # no chapters
    expect_error("name: X\nchapters: []\n")                # no pack id
    expect_error("pack: x\nname: X\nchapters:\n  - id: c\n    title: T\n    questions: []\n")  # empty questions
    expect_error("pack: x\nname: X\nchapters:\n  - id: c\n    title: T\n    questions:\n      - text: \"\"\n")  # empty text
    expect_error("pack: x\nname: X\nchapters:\n  - id: c\n    title: T\n    questions:\n      - text: q\n        tier: STRANGERS\n")  # bad tier


def test_missing_pack_rejected():
    with pytest.raises(PackError):
        load_pack("does-not-exist")


def test_own_packs_shadow_builtin(tmp_path):
    own = tmp_path / "packs"
    own.mkdir()
    (own / "starter.yaml").write_text(
        "pack: starter\nname: My Starter\nchapters:\n  - id: c\n    title: C\n    questions:\n      - text: one question\n",
        encoding="utf-8")
    pack = load_pack("starter", data_dir=str(tmp_path))
    assert pack["name"] == "My Starter"
    assert len(pack["questions"]) == 1
    packs = list_packs(data_dir=str(tmp_path))
    starter = [p for p in packs if p["id"] == "starter"][0]
    assert starter["source"] == "own" and starter["questions"] == 1


def test_list_packs_builtin_only():
    packs = list_packs()
    assert any(p["id"] == "starter" and p["source"] == "builtin" for p in packs)


def test_custom_question():
    q = custom_question("What is one thing you want me to know?")
    assert q.id.startswith("q_custom_")
    assert q.chapter == "custom"
    with pytest.raises(ValueError):
        custom_question("   ")
