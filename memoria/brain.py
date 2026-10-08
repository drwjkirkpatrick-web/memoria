"""memoria.brain — the memorial mind: retrieval + grounded generation.

The proven Jetson stack:
- EmbeddingGemma 2 on :8091 (mean pooling) — "title:/text:" docs, "search:" queries
- Granite 4.0-3B on :8090 (temp 0.0) — greedy, precise, tool-call champion

Flow: question -> embed -> cosine top-k from the persona corpus -> system
prompt (FIRST RULE) -> Granite answers as the person -> offline grounding
checker verifies every claim traces to retrieved context. If the checker
fails, the memorial refuses rather than risk inventing.
"""
from __future__ import annotations
import json
import math
import urllib.request
from pathlib import Path

EMB_PORT = 8091
GEN_PORT = 8090


class BrainError(Exception):
    pass


def _post(url: str, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def servers_up() -> bool:
    try:
        _get(f"http://127.0.0.1:{EMB_PORT}/health")
        _get(f"http://127.0.0.1:{GEN_PORT}/health")
        return True
    except Exception:
        return False


# --- embeddings ---------------------------------------------------------------

def embed(texts: list[str], port: int = EMB_PORT) -> list[list[float]]:
    r = _post(f"http://127.0.0.1:{port}/v1/embeddings",
              {"input": texts, "model": "embeddinggemma-2"})
    return [d["embedding"] for d in r["data"]]


def embed_query(q: str, port: int = EMB_PORT) -> list[float]:
    """Queries use the search: prefix (proven convention)."""
    return embed([f"search: {q}"], port)[0]


def embed_doc(doc: str, title: str = "", port: int = EMB_PORT) -> list[float]:
    """Docs use the title:/text: convention from the 8GB-stack repo."""
    return embed([f"title: {title}\ntext: {doc}"], port)[0]


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def retrieve(query: str, corpus: list[dict], k: int = 4,
             emb_port: int = EMB_PORT) -> list[dict]:
    """Embed corpus + query, return top-k statements with citations."""
    if not corpus:
        return []
    doc_texts = [f"title: {s['question']}\ntext: {s['statement']}" for s in corpus]
    vecs = embed(doc_texts, emb_port)
    qv = embed_query(query, emb_port)
    scored = sorted(((cosine(qv, v), s) for v, s in zip(vecs, corpus)),
                    key=lambda t: -t[0])
    out = []
    for score, s in scored[:k]:
        d = dict(s)
        d["retrieval_score"] = round(score, 4)
        out.append(d)
    return out


# --- generation ----------------------------------------------------------------

def generate(persona_prompt: str, question: str, context: list[dict],
             gen_port: int = GEN_PORT, max_tokens: int = 400) -> str:
    """Granite answers as the person, from retrieved context only."""
    ctx = "\n\n".join(
        f"[{i+1}] (answer id {s['answer_id']}, {s['answered_at']})\n"
        f"Q: {s['question']}\nA: {s['statement']}"
        for i, s in enumerate(context))
    user = (f"Retrieved statements from the archive:\n{ctx}\n\n"
            f"Visitor asks: {question}\n\n"
            "Answer as the person, in first person, ONLY from the statements above.")
    r = _post(f"http://127.0.0.1:{gen_port}/v1/chat/completions",
              {"model": "granite4-3b", "temperature": 0.0, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": persona_prompt},
                            {"role": "user", "content": user}]})
    return r["choices"][0]["message"]["content"]


# --- offline grounding checker ---------------------------------------------------

def check_grounded(answer: str, context: list[dict]) -> dict:
    """Verify every claim in the answer traces to retrieved context.

    Offline, conservative: split into sentences; a sentence counts as grounded
    if it shares enough distinctive words with any retrieved statement.
    """
    if not answer.strip():
        return {"grounded": False, "ungrounded": ["(empty answer)"], "n_sentences": 0}
    stop = {"the", "and", "a", "an", "of", "to", "in", "it", "was", "i", "you",
            "my", "that", "this", "for", "with", "but", "on", "at", "is", "was",
            "were", "they", "not", "so", "be", "me", "we", "when", "what", "how"}
    def words(t):
        import re
        return {w for w in re.findall(r"[a-z]+", t.lower()) if w not in stop and len(w) > 2}
    ctx_words = [words(s["statement"] + " " + s["question"]) for s in context]
    import re as _re
    sentences = [s.strip() for s in _re.split(r"[.!?]+\s*", answer) if s.strip()]
    ungrounded = []
    for sent in sentences:
        sw = words(sent)
        if not sw:
            continue
        best = max((len(sw & cw) / max(len(sw), 1) for cw in ctx_words), default=0)
        if best < 0.34:  # under a third of distinctive words traced → ungrounded
            ungrounded.append(sent)
    return {"grounded": not ungrounded, "ungrounded": ungrounded,
            "n_sentences": len(sentences)}


# --- the full ask() ---------------------------------------------------------------

class MemorialBrain:
    """One person's grounded ask() — retrieval, generation, verification."""

    def __init__(self, persona: dict, emb_port: int = EMB_PORT, gen_port: int = GEN_PORT):
        self.persona = persona
        self.emb_port = emb_port
        self.gen_port = gen_port

    def ask(self, question: str, k: int = 4) -> dict:
        corpus = self.persona["corpus"]
        if not corpus:
            return {"answer": self._refusal(), "grounded": True,
                    "retrieved": [], "grounding": {"grounded": True, "ungrounded": []},
                    "refused": True}
        context = retrieve(question, corpus, k=k, emb_port=self.emb_port)
        if not context:
            return {"answer": self._refusal(), "grounded": True, "retrieved": [],
                    "grounding": {"grounded": True, "ungrounded": []}, "refused": True}
        answer = generate(self.persona["system_prompt"], question, context,
                          gen_port=self.gen_port)
        g = check_grounded(answer, context)
        if not g["grounded"]:
            # the model drifted; the memorial refuses rather than risk inventing
            return {"answer": self._refusal(), "grounded": False, "retrieved": context,
                    "grounding": g, "refused": True, "raw_answer": answer}
        return {"answer": answer, "grounded": True, "retrieved": context,
                "grounding": g, "refused": False}

    def _refusal(self) -> str:
        name = self.persona.get("name", "this person")
        return (f"I'm sorry — I never spoke about that while I could, so I can't tell "
                f"you. I'd rather say nothing than say something untrue about {name}.")


def ask(config, person_id: str, question: str) -> dict:
    """Convenience: build persona + brain and ask."""
    from .persona import Persona
    persona = Persona(config).build(person_id)
    return MemorialBrain(persona).ask(question)
