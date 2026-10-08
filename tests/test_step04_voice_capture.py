"""Step 4: voice capture — WAV io, MockRecorder, quality analysis. No hardware touched."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.voice_capture import (MockRecorder, read_wav, write_wav,
                                  ClipQuality, analyze_clip, RecordingError)


def test_wav_roundtrip(tmp_path):
    samples = [int(8000 * math.sin(2 * math.pi * 220 * i / 16000)) for i in range(1600)]
    p = tmp_path / "x.wav"
    write_wav(p, samples, rate=16000)
    rate, back = read_wav(p)
    assert rate == 16000
    assert len(back) == 1600
    assert back == samples


def test_mock_recorder_writes_valid_wav(tmp_path):
    rec = MockRecorder()
    p = rec.record(1.0, tmp_path / "clip.wav")
    assert p.is_file()
    rate, samples = read_wav(p)
    assert rate == 16000
    assert len(samples) == 16000
    assert any(abs(s) > 1000 for s in samples)  # actual tone, not silence


def test_read_wav_rejects_garbage(tmp_path):
    p = tmp_path / "junk.wav"
    p.write_bytes(b"NOTAWAV" + b"\x00" * 32)
    with pytest.raises(RecordingError):
        read_wav(p)


def test_quality_pass(tmp_path):
    MockRecorder(amplitude=8000).record(5.0, tmp_path / "good.wav")
    rep = analyze_clip(tmp_path / "good.wav")
    assert rep["verdict"] == "pass"
    assert rep["duration_s"] == 5.0
    assert rep["clipping_pct"] == 0.0


def test_quality_fail_too_short(tmp_path):
    MockRecorder(amplitude=8000).record(0.5, tmp_path / "short.wav")
    assert analyze_clip(tmp_path / "short.wav")["verdict"] == "fail"


def test_quality_fail_clipping(tmp_path):
    MockRecorder(amplitude=32000, clip=True).record(4.0, tmp_path / "clip.wav")
    rep = analyze_clip(tmp_path / "clip.wav")
    assert rep["verdict"] == "fail"
    assert rep["clipping_pct"] > 1.0


def test_quality_fail_silence(tmp_path):
    MockRecorder(amplitude=1).record(5.0, tmp_path / "silent.wav")
    rep = analyze_clip(tmp_path / "silent.wav")
    assert rep["verdict"] in ("fail", "warn")
    assert rep["rms_dbfs"] < -40


def test_quality_warn_quiet(tmp_path):
    MockRecorder(amplitude=60).record(4.0, tmp_path / "quiet.wav")
    rep = analyze_clip(tmp_path / "quiet.wav")
    assert rep["verdict"] == "warn"


def test_duration_matches_seconds(tmp_path):
    for secs in (2.0, 3.5, 8.0):
        MockRecorder().record(secs, tmp_path / f"c{secs}.wav")
        assert analyze_clip(tmp_path / f"c{secs}.wav")["duration_s"] == pytest.approx(secs, abs=0.01)


def test_silence_fraction_detected(tmp_path):
    MockRecorder(silence_fraction=0.7).record(5.0, tmp_path / "silence.wav")
    rep = analyze_clip(tmp_path / "silence.wav")
    assert rep["silence_pct"] >= 60  # leading 70% silence detected


def test_stereo_rejected(tmp_path):
    """Only 16-bit mono accepted — the pipeline standard."""
    import struct
    p = tmp_path / "stereo.wav"
    body = struct.pack("<HHIIHHH", 1, 2, 16000, 64000, 4, 16, 0)[:16]
    # fmt chunk says 2 channels
    data = bytearray(b"RIFF" + struct.pack("<I", 36) + b"WAVE")
    data += b"fmt " + struct.pack("<I", 16) + struct.pack("<HHIIHH", 1, 2, 16000, 64000, 4, 16)
    data += b"data" + struct.pack("<I", 0)
    p.write_bytes(bytes(data))
    with pytest.raises(RecordingError):
        read_wav(p)
