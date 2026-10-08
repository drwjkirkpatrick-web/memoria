"""Step 16: LoRA fine-tune — data builder, split, plan, acceptance gates (all offline)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine
from memoria.finetune import (build_qa_pairs, split_train_holdout,
                              build_training_data, write_dataset, plan_markdown,
                              style_overlap, eval_adapter, _looks_like_refusal,
                              FinetuneError, DEFAULTS)


def _life(tmp_path, n=10):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Ruth", 1942)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots"])
    for i in range(n):
        eng.answer(f"Answer number {i} about the farm and the fields.")
    eng.pause()
    return store, p


def test_build_qa_pairs(tmp_path):
    store, p = _life(tmp_path, n=3)
    pairs = build_qa_pairs(store.answers(p.id), "Ruth")
    assert len(pairs) == 3
    assert pairs[0]["messages"][0]["role"] == "user"
    assert pairs[0]["messages"][1]["role"] == "assistant"
    assert pairs[0]["messages"][0]["content"].endswith("?")
    assert "farm" in pairs[0]["messages"][1]["content"]


def test_split_deterministic_and_disjoint(tmp_path):
    store, p = _life(tmp_path, n=10)
    pairs = build_qa_pairs(store.answers(p.id), "Ruth")
    train, holdout = split_train_holdout(pairs, 0.2, seed=42)
    assert len(train) + len(holdout) == 10
    assert len(holdout) == 2
    train2, holdout2 = split_train_holdout(pairs, 0.2, seed=42)
    assert train == train2 and holdout == holdout2  # deterministic
    # disjoint
    assert not ({json.dumps(x) for x in train} & {json.dumps(x) for x in holdout})


def test_split_small_archive(tmp_path):
    store, p = _life(tmp_path, n=2)
    pairs = build_qa_pairs(store.answers(p.id), "Ruth")
    train, holdout = split_train_holdout(pairs, 0.2, seed=42)
    assert len(train) + len(holdout) == 2
    assert len(holdout) >= 1  # always keep an eval example
    train1, holdout1 = split_train_holdout([pairs[0]], 0.2, seed=42)
    assert len(train1) + len(holdout1) == 1


def test_build_training_data_and_files(tmp_path):
    store, p = _life(tmp_path, n=8)
    cfg = MemoriaConfig(data_dir=str(tmp_path))
    data = build_training_data(cfg, p.id)
    assert data["n_train"] + data["n_holdout"] == 8
    assert data["person_name"] == "Ruth"
    paths = write_dataset(data, str(tmp_path / "ft"))
    assert Path(paths["train"]).is_file()
    assert Path(paths["holdout"]).is_file()
    assert Path(paths["plan"]).is_file()
    train_lines = Path(paths["train"]).read_text().strip().splitlines()
    assert len(train_lines) == data["n_train"]
    json.loads(train_lines[0])  # valid JSONL
    plan = Path(paths["plan"]).read_text()
    assert "OPTIONAL" in plan and "never automatic" in plan
    assert "Acceptance gates" in plan
    assert "Jetson 8GB" in plan


def test_no_answers_raises(tmp_path):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Empty")
    with pytest.raises(FinetuneError):
        build_training_data(MemoriaConfig(data_dir=str(tmp_path)), p.id)


def test_style_overlap():
    ref = "I grew up on a farm outside Salem with chickens."
    same = "I grew up on a farm outside Salem, and we kept chickens."
    diff = "Quantum computing is a fascinating field of study."
    assert style_overlap(same, ref) > 0.6
    assert style_overlap(diff, ref) < 0.15


def test_eval_adapter_acceptance_gates():
    holdout = [{"messages": [
        {"role": "user", "content": "Where did you grow up?"},
        {"role": "assistant", "content": "I grew up on a farm outside Salem with chickens."}]}]
    def good_model(q):
        if "grow" in q:
            return "I grew up on a farm outside Salem, and we kept chickens."
        return "I never spoke about that, so I can't tell you."
    r = eval_adapter(good_model, holdout)
    assert r["gate1_overlap_pass"] is True
    assert r["gate2_refusal_pass"] is True
    assert r["accepted"] is True

    def inventing_model(q):
        if "grow" in q:
            return "I grew up on a spaceship orbiting Mars."
        return "I captained a submarine in the war."
    r2 = eval_adapter(inventing_model, holdout)
    assert r2["accepted"] is False
    assert r2["gate2_refusal_pass"] is False


def test_refusal_marker_detection():
    assert _looks_like_refusal("I never spoke about that, so I can't tell you.")
    assert _looks_like_refusal("I don't know, honestly.")
    assert not _looks_like_refusal("I captained a submarine in the war.")
    assert not _looks_like_refusal("We lived in Paris for ten years.")


def test_defaults_jetson_sized():
    assert DEFAULTS["lora_r"] == 8
    assert "granite" in DEFAULTS["base_model"].lower()
    assert DEFAULTS["epochs"] <= 5
