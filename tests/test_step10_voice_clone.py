"""Step 10: voice cloning — VoicePrint measurement, ToneCloneBackend, quality gate."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore
from memoria.voice_capture import MockRecorder, write_wav
from memoria.voicebank import Voicebank
from memoria.voice_clone import (VoicePrint, ToneCloneBackend, quality_gate,
                                 VoiceCloneError)


def _clips(tmp_path, n=6, freq=200.0, rate=16000):
    """Synthetic 'person' clips: n tones of `freq` Hz, ~6s each."""
    out = []
    for i in range(n):
        samples = [int(6000 * math.sin(2 * math.pi * freq * t / rate))
                   for t in range(int(6 * rate))]
        p = tmp_path / f"clip{i}.wav"
        write_wav(p, samples, rate=rate)
        out.append({"path": str(p), "duration_s": 6.0,
                    "text": "the quick brown fox jumps over the lazy dog"})
    return out


def test_voice_print_measures(tmp_path):
    clips = _clips(tmp_path, freq=200.0)
    vp = VoicePrint.from_clips([c["path"] for c in clips], [c["text"] for c in clips])
    d = vp.to_dict()
    assert d["n_clips"] == 6
    assert 120 <= d["pitch_hz"] <= 280   # 200 Hz tones measured near 200
    assert d["energy"] > 0
    assert 1.0 <= d["rate_wps"] <= 2.0   # 9 words / 6s = 1.5 w/s


def test_voice_print_empty_rejected():
    with pytest.raises(VoiceCloneError):
        VoicePrint.from_clips([])


def test_voice_print_short_clips_skipped(tmp_path):
    # one 0.5s clip only — skipped, nothing measurable
    samples = [int(6000 * math.sin(2 * math.pi * 200 * t / 16000))
               for t in range(int(0.5 * 16000))]
    write_wav(tmp_path / "tiny.wav", samples, rate=16000)
    with pytest.raises(VoiceCloneError):
        VoicePrint.from_clips([str(tmp_path / "tiny.wav")])


def test_tone_clone_backend(tmp_path):
    clips = _clips(tmp_path)
    backend = ToneCloneBackend(MemoriaConfig(data_dir=str(tmp_path)))
    assert backend.available() is True
    art = backend.clone(None, clips)
    assert art["backend"] == "tone-clone"
    assert art["voice_print"]["n_clips"] == 6
    assert art["base_speaker"].startswith("kokoro")


def test_quality_gate_accepts_close_match():
    a = VoicePrint(pitch_hz=200, energy=5000, rate_wps=2.5, n_clips=6)
    b = VoicePrint(pitch_hz=220, energy=4000, rate_wps=2.9, n_clips=6)
    assert quality_gate(a, b) is True


def test_quality_gate_rejects_pitch_miss():
    a = VoicePrint(pitch_hz=200, energy=5000, rate_wps=2.5, n_clips=6)
    b = VoicePrint(pitch_hz=350, energy=5000, rate_wps=2.5, n_clips=6)  # +75% pitch
    assert quality_gate(a, b) is False


def test_quality_gate_rejects_rate_miss():
    a = VoicePrint(pitch_hz=200, energy=5000, rate_wps=2.5, n_clips=6)
    b = VoicePrint(pitch_hz=200, energy=5000, rate_wps=5.0, n_clips=6)  # 2x rate
    assert quality_gate(a, b) is False


def test_quality_gate_zero_pitch_safe():
    a = VoicePrint(pitch_hz=0, energy=0, rate_wps=0, n_clips=0)
    b = VoicePrint(pitch_hz=200, energy=100, rate_wps=3, n_clips=1)
    assert quality_gate(a, b) is False


def test_synthesize_requires_text(tmp_path):
    backend = ToneCloneBackend(MemoriaConfig(data_dir=str(tmp_path)))
    with pytest.raises(VoiceCloneError):
        backend.synthesize("", "af_heart", "/tmp/x.wav")


def test_full_pipeline_clips_to_clone(tmp_path):
    """Voicebank passing clips -> clone -> gate accepts (same source clips)."""
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Ruth")
    vb = Voicebank(MemoriaConfig(data_dir=str(tmp_path)), MockRecorder(freq=200.0))
    for i in range(5):
        vb.record_script_line(p.id, i, seconds=6.0)
    rep = vb.report(p.id)
    assert rep["ready"] is True
    backend = ToneCloneBackend(MemoriaConfig(data_dir=str(tmp_path)))
    art = backend.clone(p.id, vb.ready_clips(p.id))
    assert art["voice_print"]["n_clips"] == 5
