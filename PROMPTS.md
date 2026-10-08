# memoria — A Digital Gravestone

**STATUS: COMPLETE** — all 20 prompts built, one commit each. 155 tests green.

**Purpose:** a person sits down while they are alive, answers questions in their own
words, lends their voice, and leaves behind a memorial that can speak as them —
answer, remember, and tell the stories of a life — for the people who come after.

Three abilities:
1. **Interview** — guided questions whose answers are saved for future generations.
2. **Voice** — train a TTS voice from recordings of the person.
3. **Memorial LLM** — a local model that answers *like the person*, grounded strictly
   in what they actually said. Never invented.

## Conventions (learned from the-pass)

- One commit per prompt. Tests green before commit.
- Mock-first: hardware (mic, TTS engines, LLM servers) lives behind one-method interfaces.
- **No invented data** — the memorial may only speak from the archive; when it does not
  know, it says so gently. This is the project's first invariant.
- Human gates: sealed letters open only on a date rule or explicit executor approval.
- Real interview data lives OUTSIDE the repo (`~/memoria-data/`), never in git.
- Privacy-first: everything is PRIVATE tier by default.
- Jetson 8GB: one heavy model at a time; services behind the proven launch conventions.

## The 20 build prompts

**Phase 1 — Foundation**
1. **Scaffold the grove.** Python package `memoria`, config (data dir, schema version),
   core data model (Person, Question, Answer, InterviewSession, Letter, VoiceSample),
   atomic-write + sha256 utils, pytest harness. Accept: model round-trips pass.
2. **Question packs.** YAML-driven interview library; 8 life chapters (roots, growing,
   love, work, wisdom, regrets, joy, farewells) with a starter pack of 80 questions;
   loader with strict validation; custom questions. Accept: pack loads, malformed YAML rejected.
3. **Interview engine.** Session lifecycle: start, ask, record, skip, pause, resume;
   per-answer persistence; completion summary; `python -m memoria interview` CLI.
   Accept: full lifecycle + resume tests green.
4. **Voice capture (mock-first).** `Recorder` contract; MockRecorder writes synthetic
   WAVs; SoxRecorder for real hardware; pure-stdlib WAV quality analysis (duration,
   clipping %, silence %). Accept: tests never touch hardware.
5. **The archive.** Per-person directory tree; checksummed manifest; `verify()` detects
   tamper; exports: JSON bundle + Markdown "century file" (human-readable, self-describing,
   no proprietary formats). Accept: tamper detected, century file readable.

**Phase 2 — The Record**
6. **Life timeline.** Organize answers into chapters + keyword index; search returns
   answers with citations back to exact answer ids. Accept: citations resolve.
7. **Legacy letters.** Sealed messages to a person or occasion; unlock rules:
   on-date or executor-approval (human gate); sealed bodies never leak into exports.
   Accept: gate logic tested both ways.
8. **Consent and tiers.** PUBLIC / FAMILY / PRIVATE on answers and letters; executor
   sees all; exports honor the viewer's tier; delete-person removes everything.
   Accept: tier filtering tested in every export path.

**Phase 3 — Voice**
9. **Voicebank.** Guided reading script for phoneme coverage; collects clips; quality
   report per clip (SNR proxy, clipping, silence, duration) with pass/warn/fail.
   Accept: report math verified on synthetic WAVs.
10. **Voice cloning pipeline.** `VoiceBackend` interface; first impl clones tone onto a
    base speaker (Kokoro/Piper stack on the Jetson); voice-print artifact; quality gate
    before accepting a clone; graceful fallback to a stock voice. Accept: interface + gate tests.
11. **TTS service.** FastAPI on :8092 — /synthesize, /voices, /health; no text retained
    in logs; hash-keyed audio cache; launch script with Jetson conventions.
    Accept: route + cache + privacy tests green.
12. **Voice verification.** A/B harness: original vs synthesized (spectral stats, rate);
    a human MOS checklist file (the real quality gate is human ears).
    Accept: report generation from pairs.
13. **NeuTTS Air backend (optional).** Second `VoiceBackend` for NeuTTS Air (currently
    HF-gated); config-driven selection; clean "backend unavailable" path.
    Accept: registration/selection/unavailable tests with mocks.

**Phase 4 — The Memorial Mind**
14. **Persona corpus.** From the archive: style profile (sentence length, favorite words,
    signature phrases), first-person statement corpus, and the persona system prompt whose
    first rule is: answer ONLY from the archive; refuse gracefully otherwise.
    Accept: empty-archive refusal works.
15. **Memorial brain (RAG).** Our proven stack: EmbeddingGemma 2 (:8091, mean pooling)
    + Granite (:8090, temp 0.0); retrieve top-k statements; grounded generation; offline
    grounding checker verifies every claim traces to retrieved context.
    Accept: ask/refuse paths tested against mock servers.
16. **LoRA fine-tune (advanced).** Q&A → chat-format training data with held-out split;
    LoRA plan sized for the Jetson (explicit-run only); merged-GGUF export runbook;
    eval: held-out overlap + out-of-archive refusal. Accept: data builder + dry-run tests.
17. **Memorial server.** Unified API on :8093: /ask (grounded answer + voice in one call),
    /timeline, /letters (rule-gated), visitor vs family auth, audit log, rate limits.
    Accept: route contracts with mocked brain and voice.

**Phase 5 — Presence**
18. **Visitor space.** Single-file HTML/JS page: ask a question → text answer in the
    person's voice plays; browse the timeline; letters show sealed until their rule.
    Calm, organic design. QR code linking a physical marker to the page.
    Accept: page renders against the API contract.
19. **Keeper operations.** Backup/restore to multiple targets; archive integrity verify;
    media dedupe; systemd + launch scripts (setsid, one-model rule); "when the Jetson
    dies" migration runbook via century-file export. Accept: backup/restore round-trip.
20. **Letters to the future.** README, ETHICS.md (consent, dignity, executor duties,
    the no-invention promise), RUNBOOK.md, century-file format spec, LICENSE, and a
    final end-to-end smoke test: fixtures → interview → archive → ask (mock) → voice
    (mock) → restore. This is the project's own headstone.
