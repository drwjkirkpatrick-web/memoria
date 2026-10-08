"""Step 12: voice verification — A/B pairs, spectral stats, MOS checklist."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.voice_capture import write_wav, read_wav
from memoria.voice_verify import (compare_pair, auto_verdict, mos_checklist,
                                  verify_voice, _spectral_stats, VerifyError)


def _tone_wav(path, freq, secs=4.0, rate=16000, amp=6000):
    samples = [int(amp * math.sin(2 * math.pi * freq * t / rate))
               for t in range(int(secs * rate))]
    write_wav(path, samples, rate=rate)
    return str(path)


def test_spectral_stats_measures_brightness():
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        low = _tone_wav(Path(d) / "low.wav", 150)
        high = _tone_wav(Path(d) / "high.wav", 900)
        r1, s1 = read_wav(low)
        r2, s2 = read_wav(high)
        a = _spectral_stats(s1, r1)
        b = _spectral_stats(s2, r2)
        assert b["brightness"] > a["brightness"] * 3  # brighter tone measured


def test_compare_pair_deltas(tmp_path):
    o = _tone_wav(tmp_path / "orig.wav", 220)
    s = _tone_wav(tmp_path / "synth.wav", 230)
    pair = compare_pair(o, s, "the quick brown fox", "the quick brown fox")
    assert pair["original"]["duration_s"] == 4.0
    assert pair["deltas"]["brightness_ratio"] == pytest.approx(230 / 220, abs=0.05)
    assert pair["deltas"]["rate_ratio"] == pytest.approx(1.0, abs=0.01)


def test_auto_verdict_close():
    pair = {"deltas": {"brightness_ratio": 1.05, "energy_ratio": 0.9,
                       "rate_ratio": 1.1, "duration_ratio": 1.0}}
    assert auto_verdict(pair) == "close"


def test_auto_verdict_investigate():
    pair = {"deltas": {"brightness_ratio": 3.0, "energy_ratio": 0.9,
                       "rate_ratio": 0.2, "duration_ratio": 1.0}}
    assert auto_verdict(pair) == "investigate"


def test_mos_checklist_file(tmp_path):
    o = _tone_wav(tmp_path / "orig.wav", 220)
    s = _tone_wav(tmp_path / "synth.wav", 220)
    pair = compare_pair(o, s, "hello", "hello")
    md = mos_checklist([pair])
    assert "human listening checklist" in md
    assert "Pair 1" in md
    assert "Mean MOS" in md
    assert ">= 3.5" in md
    (tmp_path / "checklist.md").write_text(md, encoding="utf-8")  # writable


def test_verify_voice_full_report(tmp_path):
    origs = [{"path": _tone_wav(tmp_path / "o1.wav", 220), "text": "one two three"},
             {"path": _tone_wav(tmp_path / "o2.wav", 220), "text": "four five six"}]
    synths = [{"path": _tone_wav(tmp_path / "s1.wav", 225), "text": "one two three"},
              {"path": _tone_wav(tmp_path / "s2.wav", 225), "text": "four five six"}]
    rep = verify_voice(origs, synths)
    assert len(rep["pairs"]) == 2
    assert rep["all_close"] in (True, False)
    assert "checklist_markdown" in rep
    # machine verdicts computed
    assert all(v in ("close", "review", "investigate") for v in rep["machine_verdicts"])


def test_verify_voice_rejects_mismatch():
    with pytest.raises(VerifyError):
        verify_voice([{"path": "x", "text": "t"}], [])
    with pytest.raises(VerifyError):
        verify_voice([], [])
