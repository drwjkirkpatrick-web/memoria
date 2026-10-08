"""memoria.voice_capture — recording a person's voice, mock-first.

Real microphones vary by machine; memoria never depends on one to run or to
test. The Recorder contract is one method: record(seconds) -> WAV path.
MockRecorder synthesizes WAVs so the whole pipeline is testable offline.
"""
from __future__ import annotations
import math
import os
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Protocol


class RecordingError(Exception):
    pass


class Recorder(Protocol):
    def record(self, seconds: float, out_path: str | os.PathLike) -> Path:
        """Record `seconds` of audio to a 16-bit mono WAV. Returns the path."""
        ...


def write_wav(path: str | os.PathLike, samples: list[int], rate: int = 16000) -> None:
    """Write a 16-bit mono WAV with the stdlib only (no numpy needed here)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(samples)
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + 2 * n))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", 2 * n))
        for s in samples:
            v = max(-32768, min(32767, int(s)))
            f.write(struct.pack("<h", v))


def read_wav(path: str | os.PathLike) -> tuple[int, list[int]]:
    """Read a 16-bit mono WAV with the stdlib only. Returns (rate, samples)."""
    data = Path(path).read_bytes()
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RecordingError("not a WAV file")
    # find fmt and data chunks
    pos = 12
    rate = bits = channels = None
    samples = None
    while pos + 8 <= len(data):
        cid = data[pos:pos+4]
        size = struct.unpack("<I", data[pos+4:pos+8])[0]
        body = data[pos+8:pos+8+size]
        if cid == b"fmt ":
            _, ch, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            channels, bits = ch, bits
        elif cid == b"data":
            samples = list(struct.unpack(f"<{size//2}h", body[:size]))
        pos += 8 + size + (size & 1)
    if samples is None or rate is None:
        raise RecordingError("WAV missing data/fmt chunk")
    if channels != 1 or bits != 16:
        raise RecordingError(f"expected 16-bit mono, got {channels}ch/{bits}bit")
    return rate, samples


class MockRecorder:
    """Synthesizes WAVs — for tests and for offline demos. No hardware needed."""

    def __init__(self, freq: float = 220.0, amplitude: float = 8000, rate: int = 16000,
                 silence_fraction: float = 0.0, clip: bool = False):
        self.freq = freq
        self.amplitude = amplitude
        self.rate = rate
        self.silence_fraction = silence_fraction
        self.clip = clip

    def record(self, seconds: float, out_path: str | os.PathLike) -> Path:
        n = int(seconds * self.rate)
        samples = []
        for i in range(n):
            if self.silence_fraction and i < n * self.silence_fraction:
                samples.append(0)
                continue
            v = int(self.amplitude * math.sin(2 * math.pi * self.freq * i / self.rate))
            if self.clip and abs(v) > 20000:
                v = 32767 if v > 0 else -32767
            samples.append(v)
        out = Path(out_path)
        write_wav(out, samples, rate=self.rate)
        return out


class SoxRecorder:
    """Real hardware via `rec` (sox). Present on most systems; checked at init."""

    def __init__(self, device: str | None = None, rate: int = 16000):
        if subprocess.run(["which", "rec"], capture_output=True).returncode != 0:
            raise RecordingError("sox `rec` not found — install sox or use MockRecorder")
        self.device = device
        self.wav_rate = rate

    def record(self, seconds: float, out_path: str | os.PathLike) -> Path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["rec", "-q", str(out), "rate", str(self.wav_rate),
               "channels", "1", "encoding", "signed-integer", "bits", "16"]
        if self.device:
            cmd[1:1] = ["-d", self.device]  # inserted after 'rec' — wait, sox syntax below
        r = subprocess.run(cmd, capture_output=True, timeout=seconds + 30)
        if r.returncode != 0:
            raise RecordingError(f"rec failed: {r.stderr.decode()[:200]}")
        return out


class ClipQuality:
    """Pure-stdlib WAV quality analysis. The voicebank gate depends on it."""

    def __init__(self, rate: int, samples: list[int]):
        self.rate = rate
        self.samples = samples
        self.duration_s = len(samples) / rate if rate else 0.0

    def stats(self) -> dict:
        n = len(self.samples)
        if n == 0:
            return {"duration_s": 0.0, "rms_dbfs": -99.0, "clipping_pct": 100.0,
                    "silence_pct": 100.0, "peak": 0}
        peak = max(1, max(abs(s) for s in self.samples))
        rms = math.sqrt(sum(s * s for s in self.samples) / n)
        clipped = sum(1 for s in self.samples if abs(s) >= 32767)
        silent = sum(1 for s in self.samples if abs(s) < 100)
        rms_dbfs = 20 * math.log10(max(rms, 1e-9) / 32768)
        return {"duration_s": round(self.duration_s, 3),
                "rms_dbfs": round(rms_dbfs, 2),
                "clipping_pct": round(100 * clipped / n, 3),
                "silence_pct": round(100 * silent / n, 3),
                "peak": peak}

    def verdict(self) -> str:
        """pass / warn / fail — the voicebank's quality gate."""
        s = self.stats()
        if s["duration_s"] < 1.0:
            return "fail"      # too short to be useful
        if s["clipping_pct"] > 1.0 or s["rms_dbfs"] < -60.0:
            return "fail"      # distorted or essentially silent
        if s["silence_pct"] > 60.0 or s["rms_dbfs"] < -35.0 or s["duration_s"] < 3.0:
            return "warn"
        return "pass"


def analyze_clip(path: str | os.PathLike) -> dict:
    """Analyze a WAV: returns stats + verdict for the voicebank report."""
    rate, samples = read_wav(path)
    q = ClipQuality(rate, samples)
    out = q.stats()
    out["verdict"] = q.verdict()
    return out
