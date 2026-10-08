"""memoria.timeline — the shape of a life, and a way to search it.

Answers are organized into chapters (the pack's life chapters) with a keyword
index. Search returns answers WITH CITATIONS — every result carries the exact
answer id, question text, and chapter, so any claim can be traced back to the
person's own words.
"""
from __future__ import annotations
import re
from collections import Counter
from pathlib import Path

from .config import MemoriaConfig
from .interview import InterviewStore
from .archive import _chapter_of, CHAPTER_TITLES
from .models import Answer

# words too common to index
_STOP = {"the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
         "with", "was", "were", "is", "are", "i", "you", "my", "it", "that", "this",
         "we", "they", "he", "she", "as", "so", "not", "be", "have", "had", "did",
         "do", "would", "could", "what", "when", "how", "why", "who", "me", "them"}


def tokenize(text: str) -> list[str]:
    """Lowercase words, no punctuation; keeps hyphenated words as parts."""
    return re.findall(r"[a-z\u00c0-\u024f']+", text.lower())


def keywords(text: str) -> set[str]:
    return {w for w in tokenize(text) if w not in _STOP and len(w) > 2}


class TimelineEntry:
    """One answered question, positioned in a life."""

    def __init__(self, answer: Answer, chapter: str, chapter_title: str, index: int):
        self.answer_id = answer.id
        self.person_id = answer.person_id
        self.question_text = answer.question_text
        self.question_id = answer.question_id
        self.text = answer.text
        self.answered_at = answer.answered_at
        self.tier = answer.tier
        self.chapter = chapter
        self.chapter_title = chapter_title
        self.index = index  # order within the whole timeline

    def citation(self) -> dict:
        """A full citation: enough to find these exact words again, forever."""
        return {"answer_id": self.answer_id, "question_id": self.question_id,
                "question_text": self.question_text, "chapter": self.chapter,
                "answered_at": self.answered_at, "quote": self.text}

    def to_dict(self) -> dict:
        return {"answer_id": self.answer_id, "chapter": self.chapter,
                "chapter_title": self.chapter_title, "index": self.index,
                "question": self.question_text, "text": self.text,
                "answered_at": self.answered_at, "tier": self.tier}


class Timeline:
    """One person's answers as a browsable, searchable life."""

    def __init__(self, config: MemoriaConfig):
        self.config = config
        self.store = InterviewStore(config)

    def build(self, person_id: str) -> list[TimelineEntry]:
        """Entries in answer order, tagged with chapters."""
        answers = self.store.answers(person_id)
        entries = []
        for i, a in enumerate(answers):
            ch = _chapter_of(a.question_id)
            entries.append(TimelineEntry(a, ch, CHAPTER_TITLES.get(ch, ch.title()), i))
        return entries

    def chapters(self, person_id: str) -> dict[str, list[dict]]:
        """{chapter_id: [entry dicts]} in pack order."""
        entries = self.build(person_id)
        out: dict[str, list[dict]] = {}
        for e in entries:
            out.setdefault(e.chapter, []).append(e.to_dict())
        return out

    def keyword_index(self, person_id: str) -> dict[str, set[str]]:
        """word -> {answer_id}: the inverted index behind search."""
        index: dict[str, set[str]] = {}
        for e in self.build(person_id):
            for w in keywords(e.question_text + " " + e.text):
                index.setdefault(w, set()).add(e.answer_id)
        return index

    def top_keywords(self, person_id: str, limit: int = 25) -> list[tuple[str, int]]:
        """The person's most-indexed answer words — a quick sketch of a life."""
        counts = Counter()
        for e in self.build(person_id):
            counts.update(keywords(e.text))
        return counts.most_common(limit)

    def search(self, person_id: str, query: str, limit: int = 10) -> list[dict]:
        """Keyword search. Every hit carries a full citation.

        Ranking: answers matching more distinct query words rank first;
        ties break by timeline order (earlier in life first).
        """
        qwords = keywords(query)
        if not qwords:
            return []
        entries = {e.answer_id: e for e in self.build(person_id)}
        scores: dict[str, int] = {}
        for w in qwords:
            for aid in self._index_for(person_id).get(w, ()):  # inverted index
                scores[aid] = scores.get(aid, 0) + 1
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], entries[kv[0]].index))
        results = []
        for aid, score in ranked[:limit]:
            e = entries[aid]
            d = e.to_dict()
            d["match_words"] = sorted(qwords & keywords(e.question_text + " " + e.text))
            d["score"] = score
            d["citation"] = e.citation()
            results.append(d)
        return results

    # -- cached index per person --------------------------------------------
    def _index_for(self, person_id: str) -> dict[str, set[str]]:
        cache = getattr(self, "_idx_cache", None)
        if cache is None or cache[0] != person_id:
            cache = (person_id, self.keyword_index(person_id))
            self._idx_cache = cache
        return cache[1]


def search_with_citations(config: MemoriaConfig, person_id: str, query: str,
                          limit: int = 10) -> list[dict]:
    """Convenience one-liner used by the API layer."""
    return Timeline(config).search(person_id, query, limit=limit)
