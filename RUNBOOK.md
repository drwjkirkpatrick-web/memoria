# RUNBOOK.md — operating memoria

## Services (Jetson 8GB, one heavy model at a time)
- **:8092** TTS — `uvicorn memoria.tts_service:app --port 8092`
- **:8093** memorial — `uvicorn memoria.memorial_server:app --port 8093`
- **:8091** EmbeddingGemma 2 — `bash ~/projects/jetson-8gb-ai-stack/scripts/launch_emb2.sh 8091`
- **:8090** Granite 4.0-3B — `bash ~/projects/jetson-8gb-ai-stack/scripts/launch_granite.sh 8090`
  (launch llama-servers via setsid; q8_0 KV; GDM off — the proven conventions)

## Daily
- `python -m memoria people` — who is in the archive
- `bash scripts/stack_health.sh` (in jetson-8gb-ai-stack) — servers + RAM

## Monthly (keeper duties)
- `python -c "from memoria.keeper import backup; from memoria.config import load_config; backup(load_config())"`
- keep the tar.gz in two physical places
- `verify_all(load_config())` — manifests green

## When models change
- After any llama.cpp rebuild: re-run `pytest tests/test_step15_brain.py`
  (grounding contract) and a live /ask smoke test.

## LoRA fine-tune (explicit, never automatic)
- Build data: `finetune.build_training_data(cfg, person_id)`
- Read `plan.md` in the output bundle; run by hand off-hours.
- Acceptance: held-out overlap >= 0.5 AND >= 8/10 refusal probes pass.
  Both gates or the adapter is not used.

## When the Jetson dies
- See the migration runbook in `memoria/keeper.py::migration_runbook`:
  century files first (plain Markdown), JSON bundles second, tar.gz third.
