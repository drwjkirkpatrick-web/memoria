"""Step 20: end-to-end smoke — fixtures -> interview -> archive -> ask (mock) -> voice (mock) -> restore."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine
from memoria.archive import Archive
from memoria.timeline import Timeline
from memoria.letters import LetterBox
from memoria.persona import Persona
from memoria import brain as brain_mod
from memoria.brain import MemorialBrain
from memoria.voice_capture import MockRecorder
from memoria.voicebank import Voicebank
from memoria.voice_clone import ToneCloneBackend, VoicePrint, quality_gate
from memoria.keeper import backup, restore, verify_all
from memoria.visitor_page import render_page, qr_payload


def test_full_life_cycle(tmp_path, monkeypatch):
    cfg = MemoriaConfig(data_dir=str(tmp_path))
    store = InterviewStore(cfg)

    # 1. a person, an interview, real answers
    p = store.create_person("Ruth", 1942)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots", "joy"])
    eng.answer("I grew up on a farm outside Salem, and we kept chickens.",
               tier="FAMILY")
    eng.answer("The ocean at Cannon Beach, every summer.", tier="PUBLIC")
    eng.answer("I was afraid of the dark until I was twelve.", tier="PRIVATE")
    eng.pause()

    # 2. a sealed letter
    box = LetterBox(cfg)
    letter = box.write(p.id, "granddaughter", "Plant a garden when you are old enough.")
    r = box.readable(p.id, letter.id)
    assert r["sealed"] is True  # sealed until executor/date

    # 4. the voicebank + a tone clone (records append, so BEFORE the manifest)
    vb = Voicebank(cfg, MockRecorder())
    for i in range(5):
        vb.record_script_line(p.id, i, seconds=5.0)
    assert vb.report(p.id)["ready"] is True

    # 3. the archive: manifest LAST (it must reflect everything recorded)
    arch = Archive(cfg)
    arch.write_manifest(p.id)
    century = arch.export_markdown(p.id)
    assert "Ruth" in century.read_text(encoding="utf-8")
    assert arch.verify(p.id)["ok"] is True
    backend = ToneCloneBackend(cfg)
    art = backend.clone(p.id, vb.ready_clips(p.id))
    vp = VoicePrint(**art["voice_print"] | {"n_clips": art["voice_print"]["n_clips"]})         if False else VoicePrint(pitch_hz=art["voice_print"]["pitch_hz"],
                                  energy=art["voice_print"]["energy"],
                                  rate_wps=art["voice_print"]["rate_wps"],
                                  n_clips=art["voice_print"]["n_clips"])
    assert quality_gate(vp, vp) is True  # self-comparison passes

    # 5. the memorial mind: ask with a mocked brain (grounded, cited)
    persona = Persona(cfg).build(p.id, tier_cap="FAMILY")
    assert len(persona["corpus"]) == 2  # PUBLIC + FAMILY, not PRIVATE

    class MockBrain:
        def __init__(self, persona_): self.persona = persona_
        def ask(self, q, k=4):
            ctx = persona["corpus"][:1]
            return {"answer": ctx[0]["statement"], "refused": False, "grounded": True,
                    "retrieved": ctx, "grounding": {"grounded": True}}
    r = MockBrain(persona).ask("where did you grow up?")
    assert "farm" in r["answer"]
    assert r["retrieved"][0]["answer_id"].startswith("ans_")

    # 6. the visitor page renders against the contract
    page = render_page(api_base="http://127.0.0.1:8093", person_id=p.id)
    assert p.id in page and "/ask" in page

    # 7. backup -> restore -> verify intact
    tar = backup(cfg)
    dest = tmp_path.parent / "smoke-restore"
    if dest.exists():
        import shutil; shutil.rmtree(dest)
    res = restore(cfg, str(tar), dest_data_dir=str(dest))
    assert res["ok"] is True and res["people"] == 1
    v = verify_all(MemoriaConfig(data_dir=str(dest)))
    assert v[p.id]["ok"] is True

    # 8. the century file in the restored archive still reads
    century2 = Archive(MemoriaConfig(data_dir=str(dest))).export_markdown(p.id)
    assert "Ruth" in century2.read_text(encoding="utf-8")
    assert "chickens" in century2.read_text(encoding="utf-8")


def test_the_project_headstone(tmp_path):
    """PROMPTS.md, ETHICS.md, RUNBOOK.md, README all exist and say what they must."""
    root = Path(__file__).resolve().parents[1]
    prompts = (root / "PROMPTS.md").read_text(encoding="utf-8")
    assert "20 build prompts" in prompts
    ethics = (root / "ETHICS.md").read_text(encoding="utf-8")
    assert "never invents" in ethics.lower()
    assert "consent" in ethics.lower()
    assert "executor" in ethics.lower()
    runbook = (root / "RUNBOOK.md").read_text(encoding="utf-8")
    assert "8092" in runbook and "8093" in runbook
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "gravestone" in readme.lower()
