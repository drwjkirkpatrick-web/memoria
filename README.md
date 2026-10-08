# memoria — a digital gravestone

Record a person's answers, voice, and stories while they are here, so the people
who come after can still ask, and still hear.

**Three abilities:**
1. **Interview** — 80 guided questions in 8 life chapters, saved word-for-word, tiered PUBLIC/FAMILY/PRIVATE.
2. **Voice** — a guided reading script captures the voice; a voice-print is measured; a TTS backend speaks in the person's tone (NeuTTS Air for true cloning when its HF gate opens; Kokoro/Piper today).
3. **Memorial mind** — asks are answered *as the person*, grounded strictly in the archive via EmbeddingGemma 2 + Granite, with an offline grounding checker. **It never invents. If the archive doesn't hold the answer, the memorial says so.**

## Layout

```
memoria/
├── models.py          Person, Question, Answer, Session, Letter, VoiceSample
├── packs.py           question packs (starter: 8 chapters × 10)
├── interview.py       session engine + CLI + store
├── archive.py         checksummed manifest, tamper detect, exports
├── timeline.py        chapters + keyword search with citations
├── letters.py         sealed letters (executor key / on-date rules)
├── access.py          PUBLIC/FAMILY/PRIVATE tiers × public/family/executor roles
├── voice_capture.py   Recorder contract, WAV io, quality gate
├── voicebank.py       guided reading script + clip collection
├── voice_clone.py     VoicePrint, ToneCloneBackend, clone quality gate
├── voice_backends.py  NeuTTS (gated) > Kokoro > Piper registry
├── tts_service.py     FastAPI :8092 (synthesize/voices/health)
├── voice_verify.py    A/B harness + human MOS checklist
├── persona.py         style profile + FIRST-RULE no-invention prompt
├── brain.py           RAG (EmbeddingGemma 2 :8091 + Granite :8090)
├── finetune.py        LoRA plan (explicit-run only) + acceptance gates
├── memorial_server.py unified API :8093 (ask/voice/timeline/letters)
├── visitor_page.py    single-file organic HTML visitor space
└── keeper.py          backup/restore, verify, dedupe, migration runbook
```

## Quick start

```bash
python -m memoria interview --person "Ruth"        # guided interview
python -m memoria export --person <person_id>      # century file (Markdown)
python -m pytest tests -q                          # 153 tests
uvicorn memoria.tts_service:app --port 8092         # the voice
uvicorn memoria.memorial_server:app --port 8093    # the memorial
```

## The two invariants

1. **The memorial never invents.** Every answer traces to retrieved statements
   (checked offline); refusals are gentle and in first person.
2. **Tiers are enforced in code.** PUBLIC/FAMILY/PRIVATE content is filtered at
   every read path — answers, search, letters, the LLM corpus, exports.

Real interview data lives in `~/memoria-data/` — never in this repo.
See `ETHICS.md` for consent, dignity, and executor duties; `RUNBOOK.md`
for operations; `PROMPTS.md` for the 20-step build plan.

## Status

All 20 build steps complete. 153 tests green. Voice cloning awaits NeuTTS Air's
HF gate (registry degrades to Kokoro/Piper meanwhile); LoRA fine-tuning is
plan + data builder, explicit-run only.
