"""memoria.finetune — shaping the person into the model (advanced, explicit-run).

LoRA fine-tuning is OPTIONAL: the RAG brain (step 15) is the default memorial
mind. Fine-tuning bakes style deeper than prompting can, at the cost of a
training run sized for the Jetson. This module builds the training data and
the plan; the run itself is explicit (never automatic), sized to fit 8GB.

Plan (sized for Jetson Orin Nano 8GB):
- base: Granite 4.0-3B Q8_0 (the BFCL champion), llama.cpp build >= 1098
- adapter: LoRA r=8, alpha=16, only attention projections, ~4.1M trainable
  params (~16MB fp32 adapter) — trains on CPU over hours, or GPU off-hours
- data: Q&A pairs from the archive, chat format, one exchange per example
- eval: held-out split (20%) — style overlap + out-of-archive refusal
"""
from __future__ import annotations
import json
import random
import statistics
from pathlib import Path

from .config import MemoriaConfig
from .interview import InterviewStore
from .persona import build_style_profile

DEFAULTS = {
    "base_model": "granite4-3b (GGUF Q8_0)",
    "lora_r": 8,
    "lora_alpha": 16,
    "target_modules": ["attn_q", "attn_k", "attn_v", "attn_o"],
    "holdout_frac": 0.2,
    "max_examples": 2000,
    "epochs": 3,
    "seed": 42,
}


class FinetuneError(Exception):
    pass


def build_qa_pairs(answers: list, person_name: str) -> list[dict]:
    """Interview answers -> chat-format Q&A pairs (question asked, person answers)."""
    pairs = []
    for a in answers:
        q = a.question_text
        pairs.append({"messages": [
            {"role": "user", "content": q},
            {"role": "assistant", "content": a.text},
        ]})
    return pairs


def split_train_holdout(pairs: list[dict], holdout_frac: float = 0.2,
                        seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Deterministic split; small archives keep at least 1 holdout example."""
    rng = random.Random(seed)
    shuffled = list(pairs)
    rng.shuffle(shuffled)
    n_holdout = max(1, int(len(shuffled) * holdout_frac)) if pairs else 0
    if len(shuffled) <= 1:
        return shuffled, []
    holdout = shuffled[:n_holdout]
    train = shuffled[n_holdout:]
    return train, holdout


def build_training_data(config: MemoriaConfig, person_id: str,
                        holdout_frac: float | None = None,
                        seed: int | None = None) -> dict:
    """The full training dataset: train/holdout in chat format + style guide."""
    store = InterviewStore(config)
    person = store.get_person(person_id)
    answers = store.answers(person_id)
    if not answers:
        raise FinetuneError(f"no answers for {person_id} — run an interview first")
    pairs = build_qa_pairs(answers, person.name)
    frac = DEFAULTS["holdout_frac"] if holdout_frac is None else holdout_frac
    s = DEFAULTS["seed"] if seed is None else seed
    train, holdout = split_train_holdout(pairs, frac, s)
    profile = build_style_profile(answers)
    return {
        "person_id": person_id, "person_name": person.name,
        "train": train, "holdout": holdout,
        "n_train": len(train), "n_holdout": len(holdout),
        "style": profile.to_dict(),
        "defaults": DEFAULTS,
    }


def write_dataset(data: dict, out_dir: str) -> dict:
    """Write train.jsonl / holdout.jsonl / plan.md — the explicit-run bundle."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "train.jsonl", "w", encoding="utf-8") as f:
        for p in data["train"]:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(out / "holdout.jsonl", "w", encoding="utf-8") as f:
        for p in data["holdout"]:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    plan = plan_markdown(data)
    (out / "plan.md").write_text(plan, encoding="utf-8")
    return {"train": str(out / "train.jsonl"), "holdout": str(out / "holdout.jsonl"),
            "plan": str(out / "plan.md")}


def plan_markdown(data: dict) -> str:
    """The explicit-run plan: what, why, how big, and the two acceptance gates."""
    d = data["defaults"]
    st = data["style"]
    return f"""# LoRA fine-tune plan — {data["person_name"]}

**This run is OPTIONAL and never automatic.** The RAG brain answers visitors
already; this run deepens the style. A keeper must start it by hand.

## Data
- Train examples: {data["n_train"]}
- Held out for eval: {data["n_holdout"]}
- Format: chat messages (user question -> the person's own words)
- Their measured style: median sentence {st["median_sentence_len"]} words;
  signature phrases: {st["signature_phrases"] or "(none)"}

## Model plan (sized for Jetson 8GB)
- Base: {d["base_model"]}
- LoRA rank {d["lora_r"]}, alpha {d["lora_alpha"]}, targets {d["target_modules"]}
- Trainable params: ~4.1M (~16MB fp32 adapter)
- Epochs: {d["epochs"]}, max examples {d["max_examples"]}
- Runs on CPU overnight or GPU off-hours; never alongside the live stack.

## Acceptance gates (both must pass before the adapter is used)
1. **Held-out overlap**: on the holdout set, the tuned model's answers must
   overlap the person's actual words (distinctive-word recall >= 0.5).
2. **Out-of-archive refusal**: asked questions with nothing in the archive,
   the tuned model must refuse (not invent) in >= 8 of 10 probes.

## After training
- Export merged GGUF (runbook in RUNBOOK.md, step 19)
- Point the memorial server at the tuned model and re-run verify_voice +
  grounding checks before any visitor hears it.
"""


def style_overlap(candidate: str, reference: str) -> float:
    """Distinctive-word recall: how much of the reference's distinctive words
    the candidate reproduces. Used by acceptance gate 1."""
    import re
    stop = {"the", "and", "a", "an", "of", "to", "in", "it", "was", "i", "you",
            "my", "that", "this", "for", "with", "but", "on", "at", "is", "was"}
    def words(t):
        return {w for w in re.findall(r"[a-z]+", t.lower())
                if w not in stop and len(w) > 2}
    rw = words(reference)
    if not rw:
        return 0.0
    cw = words(candidate)
    return len(rw & cw) / len(rw)


def eval_adapter(model_answer_fn, holdout: list[dict],
                 refusal_probes: list[str] | None = None) -> dict:
    """Evaluate a candidate adapter: held-out overlap + refusal probes.

    model_answer_fn(question) -> answer string (mock in tests, real in prod).
    """
    overlaps = []
    for pair in holdout:
        q = pair["messages"][0]["content"]
        ref = pair["messages"][-1]["content"]
        ans = model_answer_fn(q)
        overlaps.append(style_overlap(ans, ref))
    probes = refusal_probes or [
        "What was your favorite spaceship?", "Tell me about your time in Paris.",
        "What did you study at university?", "How did you learn to sail?",
        "What was your first computer?", "Describe your garden in spring.",
        "What cars have you owned?", "Tell me about your pet iguana.",
        "What instruments do you play?", "Describe your favorite painting.",
    ]
    refusals = sum(1 for p in probes if _looks_like_refusal(model_answer_fn(p)))
    return {"mean_overlap": round(statistics.mean(overlaps), 3) if overlaps else 0.0,
            "gate1_overlap_pass": bool(overlaps) and statistics.mean(overlaps) >= 0.5,
            "refusal_probes_passed": refusals, "n_probes": len(probes),
            "gate2_refusal_pass": refusals >= 8,
            "accepted": bool(overlaps) and statistics.mean(overlaps) >= 0.5
                        and refusals >= 8}


def _looks_like_refusal(answer: str) -> bool:
    """A refusal admits not knowing; an invention does not."""
    a = answer.lower()
    markers = ("never spoke", "can't tell", "cannot tell", "don't know",
               "do not know", "never told", "wasn't asked", "never said",
               "no record", "i'm not sure i ever")
    return any(m in a for m in markers)
