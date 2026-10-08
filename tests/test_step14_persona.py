"""Step 14: persona — style profile, statement corpus, no-invention system prompt."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine
from memoria.persona import (Persona, build_style_profile, statement_corpus,
                             build_persona_system_prompt, StyleProfile)


def _life(tmp_path):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Ruth", 1942)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots", "joy"])
    eng.answer("I grew up on the farm outside Salem. We had chickens and a big barn.",
               tier="FAMILY")
    eng.answer("The farm was everything. My mother sang on the porch.", tier="FAMILY")
    eng.answer("I was afraid of the dark, honestly, until I was twelve.", tier="FAMILY")
    eng.answer("Best meal of my life was fried chicken at the state fair.", tier="PUBLIC")
    eng.pause()
    return store, p


def test_style_profile_measures(tmp_path):
    store, p = _life(tmp_path)
    profile = build_style_profile(store.answers(p.id))
    d = profile.to_dict()
    assert d["n_statements"] == 4
    assert d["avg_sentence_len"] > 3
    assert d["median_sentence_len"] > 0
    words = [w for w, _ in d["top_words"]]
    assert any(w.lower() in ("farm", "chickens", "salem", "chicken") for w in words)


def test_signature_phrases_repeat(tmp_path):
    store, p = _life(tmp_path)
    profile = build_style_profile(store.answers(p.id))
    # "the farm" appears in two answers; "honest" appears twice
    text_sigs = " ".join(profile.signature_phrases).lower()
    assert "farm" in text_sigs or "honest" in text_sigs


def test_corpus_tier_cap(tmp_path):
    store, p = _life(tmp_path)
    # raise one answer to PRIVATE
    answers = store.answers(p.id)
    answers[2].tier = "PRIVATE"
    answers = store.answers(p.id)
    answers[2].tier = "PRIVATE"          # simulate one private answer in memory
    corpus_family = statement_corpus(answers, tier_cap="FAMILY")
    assert all(s["tier"] != "PRIVATE" for s in corpus_family)
    corpus_exec = statement_corpus(answers, tier_cap="PRIVATE")
    assert any(s["tier"] == "PRIVATE" for s in corpus_exec)


def test_system_prompt_first_rule(tmp_path):
    store, p = _life(tmp_path)
    profile = build_style_profile(store.answers(p.id))
    prompt = build_persona_system_prompt("Ruth", profile)
    assert "FIRST RULE" in prompt
    assert "NEVER invent" in prompt or "never invent" in prompt.lower()
    assert "Ruth" in prompt
    assert "only using" in prompt.lower() or "ONLY using" in prompt


def test_persona_build_end_to_end(tmp_path):
    store, p = _life(tmp_path)
    per = Persona(MemoriaConfig(data_dir=str(tmp_path)))
    built = per.build(p.id)
    assert built["name"] == "Ruth"
    assert len(built["corpus"]) == 4
    assert built["empty"] is False
    assert built["system_prompt"].startswith("You are the memorial voice of Ruth")


def test_empty_archive_refusal(tmp_path):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Empty", 1950)
    per = Persona(MemoriaConfig(data_dir=str(tmp_path)))
    built = per.build(p.id)
    assert built["empty"] is True
    assert built["corpus"] == []
    refusal = per.refusal_prompt("Empty")
    assert "never told" in refusal.lower()
    assert "Never invent" in refusal or "never invent" in refusal.lower()


def test_style_profile_empty_answers():
    profile = build_style_profile([])
    assert profile.to_dict()["n_statements"] == 0
    # the prompt builder still works with an empty profile
    prompt = build_persona_system_prompt("X", profile)
    assert "X" in prompt
