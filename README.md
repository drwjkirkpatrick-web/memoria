# memoria — a digital gravestone

Record a person's answers, voice, and stories while they are here, so the people
who come after can still ask, and still hear.

- **Interview** — guided questions saved for future generations
- **Voice** — a TTS voice trained on the person's own recordings
- **Memorial LLM** — answers like the person, grounded only in what they actually said

Status: built prompt-by-prompt; see `PROMPTS.md` for the 20-step plan and progress.

```bash
python -m memoria interview --person "Name"   # guided interview
python -m pytest tests -q                      # run the test suite
```

Real interview data lives in `~/memoria-data/` — never in this repo.

First invariant: the memorial never invents. If the archive does not hold the answer,
the memorial says so.
