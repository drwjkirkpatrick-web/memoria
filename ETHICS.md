# ETHICS.md — memoria's promises

## Consent
- The person records everything themselves, while alive, and can stop or
  delete at any time (`Viewer(role="executor").delete_person`).
- Nothing is recorded without the person's knowledge. The interview asks;
  it never scrapes.
- Consent is per-answer (tiers) and revocable per-person (delete removes
  every file and export).

## Dignity
- The memorial speaks in first person as the person — but only from what
  they actually said. **It never invents.** The grounding checker enforces
  this; a drifted answer is refused, not shown.
- A refusal is honest and warm: "I never spoke about that, so I can't tell
  you." Silence is allowed. Guessing is not.
- The voice is a tone-carrying approximation, never presented as a perfect
  re-creation. The A/B harness and human MOS checklist keep the claim honest.

## The executor's duties
- The executor key opens executor-rule letters. It is held by one living
  person at a time; rotate `<data>/config/executor_key` when the holder changes.
- The executor may delete a person entirely. Deletion is real: files, exports,
  backups that the keeper controls.
- The executor does NOT override on-date letters before their date. Dates
  are the person's word, kept past death.

## Data
- Everything is local. No text or audio leaves the device through memoria;
  TTS and LLM servers run on the same Jetson.
- Sealed letter bodies never appear in any export, API response, or backup
  until their rule is satisfied.
- The century file is plain Markdown so the record outlives every format.

## What memoria is not
- Not a simulation of a person. Not a chatbot "playing" the deceased.
  It is a curated, consented, verified record that can speak its own words.
