# memoria — a digital gravestone

*Record a person's answers, their voice, and their stories while they are here — so the people who come after can still ask, and still hear.*

![memoria](https://img.shields.io/badge/memoria-a%20digital%20gravestone-5a6b52)
![jetson](https://img.shields.io/badge/Jetson-8GB-blue)
![local-first](https://img.shields.io/badge/local--first-no%20cloud-2c2a26)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![tests](https://img.shields.io/badge/tests-155%20green-brightgreen)
![license](https://img.shields.io/badge/license-MIT-5a6b52)

---

## Why this exists

Somewhere in a shoebox there is a cassette tape of your grandmother's voice.
Nobody has a cassette player anymore.

That is the problem memoria solves. All of us are leaving behind less and less
that lasts — our photos live in cloud accounts that will close, our messages
in apps that will shut down. And the stories, the real ones, the ones someone
would actually want to hear again in fifty years? Most of those are never
recorded at all.

memoria is a small, quiet program that fixes this. A person sits down while
they are alive, answers questions in their own words, lends their voice —
and leaves behind a memorial that can still speak as them, long after.

It runs entirely on a small computer in your home. Nothing goes to any cloud.
Nothing leaves the house.

---

## What a person does

**They answer questions.** Eighty gentle questions in eight chapters of a
life — roots, growing up, love, work, wisdom, regrets, joy, and farewells.
*Where did you grow up, and what did it feel like?* *What made you laugh
hardest in your whole life?* *What do you want the people you love to know
that you have not said?*

They can skip any question. Stop anytime and pick the thread back up next
week. Every word is saved the moment it is spoken.

**They lend their voice.** A short reading script — a few sentences designed
to capture every sound a voice makes. The program measures the voice: its
pitch, its pace, its energy. Then it learns to speak in that voice's tone, so
the memorial doesn't just *say* the words — it says them the way *they* said
them.

**They write letters.** Sealed ones. To a granddaughter, to be opened on her
40th birthday. To a son, to be opened only when the family executor decides
the time is right. The program keeps them sealed — truly sealed — until the
person's own rule says otherwise.

---

## What the people who come after get

A quiet page, reached by a QR code on a physical marker. They type a question:

*"What was your earliest memory?"*

And the memorial answers — in first person, in their grandmother's own words,
in her voice's tone, with a small note showing exactly which of her recorded
answers the reply came from.

If the archive doesn't hold an answer, the memorial says so, gently:
*"I never spoke about that, so I can't tell you — but I'm glad you asked."*

---

## The promise that makes this different

**The memorial never invents.** This is the heart of the whole project,
built into the code and checked by machine at every answer: it may only speak
from what the person actually said. It will never guess, never fill in, never
make up a memory. A memorial that invents is a lie about a person — that is
the one thing memoria will not do.

**Consent is real.** Every answer is marked public, family, or private.
Visitors see only what was meant for them. Private words stay private — even
from the memorial itself.

**Nothing leaks.** Sealed letters stay sealed in every backup and every
export. Nothing is sent to any cloud. The whole thing lives on your own
hardware.

**It outlives every format.** Alongside everything else, memoria writes a
"century file" — plain Markdown text of the person's answers. It needs no
software, no accounts, nothing but the ability to read. If every computer
dies, the century file is the gravestone.

---

## What's inside (for the technically curious)

- **The interview** — 80 questions, pause and resume, every word saved as it's spoken
- **The archive** — checksummed records that detect tampering, with JSON and Markdown exports
- **The voice** — a reading script, quality gates on every clip, a measured voice-print, and a speaking pipeline (Kokoro/Piper today; NeuTTS Air zero-shot cloning when its access gate opens)
- **The mind** — retrieval from the person's actual words (EmbeddingGemma 2), answered by a local LLM (Granite 4.0-3B), verified by a grounding checker that refuses rather than risks inventing
- **The gates** — sealed letters, consent tiers, a real executor key
- **The keeper's tools** — one-command backups, restore that verifies itself, and a migration runbook for the day the hardware dies

Designed for a Jetson Orin Nano 8GB — a $250 computer the size of a candy bar
running the whole memorial on 8 gigabytes of memory, alongside a RAG embedding
model and an agent, with room to spare.

---

## Quick start

```bash
python -m memoria interview --person "Ruth"        # the guided interview
python -m memoria export --person <person_id>      # the century file
python -m pytest tests -q                          # 155 tests, all green
uvicorn memoria.memorial_server:app --port 8093    # the memorial itself
```

The full operations guide is in `RUNBOOK.md`; the promises in detail are in
`ETHICS.md`; the 20-step build plan with one commit per step is in
`PROMPTS.md`.

---

*Nothing here is a simulation of a person. It is a record, given willingly in
their own words — kept safely, and allowed to speak.*

*Light the candle. Sit down. Ask.*
