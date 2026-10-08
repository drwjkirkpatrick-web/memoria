"""Step 9: voicebank — guided script, clip collection, quality gate, readiness."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore
from memoria.voice_capture import MockRecorder
from memoria.voicebank import Voicebank, VoicebankError, READING_SCRIPT


def _env(tmp_path, amplitude=8000):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Ruth", 1942)
    return store, p, Voicebank(MemoriaConfig(data_dir=str(tmp_path)),
                               MockRecorder(amplitude=amplitude))


def test_reading_script_exists():
    assert len(READING_SCRIPT) == 10
    assert all(isinstance(s, str) and len(s) > 20 for s in READING_SCRIPT)


def test_record_line_makes_quality_reported_clip(tmp_path):
    store, p, vb = _env(tmp_path)
    r = vb.record_script_line(p.id, 0, seconds=6.0)
    assert r["clip_id"].startswith("vs_")
    assert r["report"]["verdict"] == "pass"
    assert r["accepted"] is True
    assert Path(r["path"]).is_file()
    # persisted in the store
    samples = store.voice_samples(p.id)
    assert len(samples) == 1
    assert samples[0].quality_report["verdict"] == "pass"


def test_line_index_bounds(tmp_path):
    store, p, vb = _env(tmp_path)
    with pytest.raises(VoicebankError):
        vb.record_script_line(p.id, 99)
    with pytest.raises(VoicebankError):
        vb.record_script_line(p.id, -1)


def test_quality_gate_rejects_bad_clips(tmp_path):
    # quiet recorder -> warn/fail verdicts, not accepted
    store, p, vb = _env(tmp_path, amplitude=50)
    r = vb.record_script_line(p.id, 0, seconds=4.0)
    assert r["accepted"] is False
    assert r["report"]["verdict"] in ("warn", "fail")
    # readiness is False: no passing clips
    rep = vb.report(p.id)
    assert rep["pass"] == 0 and rep["ready"] is False


def test_readiness_needs_five_passes(tmp_path):
    store, p, vb = _env(tmp_path)
    for i in range(4):
        vb.record_script_line(p.id, i, seconds=6.0)
    assert vb.report(p.id)["ready"] is False
    vb.record_script_line(p.id, 4, seconds=6.0)
    rep = vb.report(p.id)
    assert rep["pass"] == 5 and rep["ready"] is True
    assert rep["clips"] == 5 and rep["warn"] == 0 and rep["fail"] == 0


def test_ready_clips_returns_only_passes(tmp_path):
    store, p, vb = _env(tmp_path)
    vb.record_script_line(p.id, 0, seconds=6.0)             # pass
    vb_bad = Voicebank(MemoriaConfig(data_dir=str(tmp_path)), MockRecorder(amplitude=50))
    vb_bad.record_script_line(p.id, 1, seconds=4.0)          # warn/fail
    vb.record_script_line(p.id, 2, seconds=6.0)             # pass
    ready = vb.ready_clips(p.id)
    assert len(ready) == 2
    assert all(Path(c["path"]).is_file() for c in ready)
    assert all(c["clip_id"].startswith("vs_") for c in ready)


def test_total_duration_accumulates(tmp_path):
    store, p, vb = _env(tmp_path)
    vb.record_script_line(p.id, 0, seconds=6.0)
    vb.record_script_line(p.id, 1, seconds=8.0)
    assert vb.report(p.id)["total_duration_s"] == pytest.approx(14.0, abs=0.2)


def test_unknown_person_rejected(tmp_path):
    vb = Voicebank(MemoriaConfig(data_dir=str(tmp_path)), MockRecorder())
    with pytest.raises(Exception):
        vb.record_script_line("person_missing", 0)
