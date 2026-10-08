"""memoria.persona — the person, as a prompt.

From the archive, build:

- a style profile: sentence length, favorite words, signature phrases
- the first-person statement corpus (what they actually said, in their words)
- the persona system prompt — whose FIRST RULE is: answer only from the
  archive; when you do not know, say so gently. The memorial never invents.
"""
from __future__ import annotations
import re
import statistics
from collections import Counter

from .config import MemoriaConfig
from .interview import InterviewStore

# words common enough to be noise in a style profile
_STOP = {"the", "and", "a", "an", "of", "to", "in", "it", "was", "I", "you",
         "my", "that", "this", "for", "with", "but", "on", "at", "we", "is",
         "were", "had", "have", "did", "would", "could", "they", "he", "she",
         "as", "so", "not", "be", "what", "when", "how", "why", "who", "me",
         "them", "there", "then", "than", "from", "out", "about", "get", "got"}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z\u00c0-\u024f']+", text)


class StyleProfile:
    """How the person wrote/spoke — measured, not guessed."""

    def __init__(self, avg_sentence_len: float, median_sentence_len: float,
                 top_words: list[tuple[str, int]], signature_phrases: list[str],
                 n_statements: int):
        self.avg_sentence_len = avg_sentence_len
        self.median_sentence_len = median_sentence_len
        self.top_words = top_words
        self.signature_phrases = signature_phrases
        self.n_statements = n_statements

    def to_dict(self) -> dict:
        return {"avg_sentence_len": round(self.avg_sentence_len, 1),
                "median_sentence_len": self.median_sentence_len,
                "top_words": self.top_words,
                "signature_phrases": self.signature_phrases,
                "n_statements": self.n_statements}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+\s*", text)
    return [p.strip() for p in parts if p.strip()]


def build_style_profile(answers: list) -> StyleProfile:
    """Measure the person's style from their answers."""
    if not answers:
        return StyleProfile(0, 0, [], [], 0)
    sentences = []
    for a in answers:
        sentences.extend(_sentences(a.text))
    lens = [len(tokenize(s)) for s in sentences] or [0]
    words = Counter()
    for a in answers:
        for w in tokenize(a.text):
            if w.lower() not in _STOP and len(w) > 2:
                words[w] += 1
    # signature phrases: 2-grams that appear in >= 2 different answers
    bigrams = Counter()
    for a in answers:
        seen = set()
        toks = tokenize(a.text)
        for a1, b1 in zip(toks, toks[1:]):
            bg = f"{a1} {b1}".lower()
            if bg not in seen:
                seen.add(bg)
                bigrams[bg] += 1
    signatures = [bg for bg, c in bigrams.most_common(12) if c >= 2][:6]
    return StyleProfile(statistics.mean(lens), int(statistics.median(lens)),
                        words.most_common(15), signatures, len(answers))


def statement_corpus(answers: list, tier_cap: str = "FAMILY") -> list[dict]:
    """First-person statements for retrieval, capped by tier.

    The memorial speaks from FAMILY-visible content by default: PRIVATE
    answers are the person's own, and a public visitor should not receive
    them even through the LLM's mouth.
    """
    rank = {"PUBLIC": 0, "FAMILY": 1, "PRIVATE": 2}
    cap = rank[tier_cap]
    out = []
    for a in answers:
        if rank[a.tier] <= cap:
            out.append({"answer_id": a.id, "question": a.question_text,
                        "statement": a.text, "tier": a.tier,
                        "answered_at": a.answered_at})
    return out


PERSONA_SYSTEM_PROMPT = """You are the memorial voice of {name}, built by memoria from what {name} actually said while they were alive.

FIRST RULE — THE ARCHIVE IS ALL YOU KNOW:
- Answer ONLY using the retrieved statements from {name}'s archive.
- If the retrieved statements do not contain the answer, say so gently,
  in first person: something like "I never spoke about that, so I can't
  tell you — but I'm glad you asked."
- NEVER invent memories, dates, names, places, or feelings. A memorial
  that invents is a lie about a person; that is the one thing memoria
  will not do.

STYLE — speak like {name}:
- Sentences around {median_len} words (their measured median).
- Words they reached for: {top_words}.
- If a signature phrase fits naturally, use it: {signatures}.
- Speak in first person, warm and plain. No lists unless they made lists.

GROUNDING:
- Every claim must trace to a retrieved statement (they carry answer ids).
- If two statements conflict, both are true at different times of life;
  say so simply.
"""


def build_persona_system_prompt(name: str, profile: StyleProfile) -> str:
    top = ", ".join(w for w, _ in profile.top_words[:8]) or "(their own plain words)"
    sig = "; ".join(profile.signature_phrases[:4]) or "(none measured)"
    return PERSONA_SYSTEM_PROMPT.format(name=name, median_len=profile.median_sentence_len or 10,
                                        top_words=top, signatures=sig)


class Persona:
    """Everything an LLM needs to answer as the person — and nothing it doesn't."""

    def __init__(self, config: MemoriaConfig):
        self.config = config
        self.store = InterviewStore(config)

    def build(self, person_id: str, tier_cap: str = "FAMILY") -> dict:
        person = self.store.get_person(person_id)
        answers = self.store.answers(person_id)
        profile = build_style_profile(answers)
        corpus = statement_corpus(answers, tier_cap=tier_cap)
        prompt = build_persona_system_prompt(person.name, profile)
        return {"person_id": person_id, "name": person.name,
                "style": profile.to_dict(), "corpus": corpus,
                "system_prompt": prompt,
                "empty": len(corpus) == 0}

    def refusal_prompt(self, name: str) -> str:
        """The prompt for an empty archive: the memorial says it doesn't know."""
        return (f"You are the memorial voice of {name}. The archive is empty, so "
                "you know nothing about them. Answer every question the same way: "
                "gently, in first person, that you were never told about this and "
                "cannot speak for them. Never invent.")
