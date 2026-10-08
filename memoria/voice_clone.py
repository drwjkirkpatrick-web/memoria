"""memoria.voice_clone — the person's voice, re-created.

The VoiceBackend contract is one method: synthesize(text, voice_ref) -> WAV path.
The first implementation is ToneCloneBackend: it analyzes the person's clips
(pitch, energy, rate) and clones that tone onto a base speaker — the Kokoro/Piper
stack proven on the Jetson. No backend ever sends text or audio off-device.

A quality gate runs before a clone is accepted: the clone must be close enough
to the person's measured voice, or memoria falls back to a stock voice rather
than present an impersonation that misses.
"""
from __future__ import annotations
import statistics
import uuid
from pathlib import Path
from typing import Protocol

from .config import MemoriaConfig
from .interview import InterviewStore
from .voice_capture import read_wav


class VoiceCloneError(Exception):
    pass


class VoiceBackend(Protocol):
    """One method: synthesize speech. Implementations: local models only."""

    def synthesize(self, text: str, voice: str, out_path: str) -> Path:
        ...


class VoicePrint:
    """Measured statistics of the person's voice, from their clips.

    pitch_hz  — median fundamental frequency estimate
    energy    — median absolute sample amplitude
    rate_wps  — words per second the person actually speaks
    """

    def __init__(self, pitch_hz: float, energy: float, rate_wps: float,
                 n_clips: int, source: str = "clips"):
        self.pitch_hz = pitch_hz
        self.energy = energy
        self.rate_wps = float(f"{rate_wps:.2f}")
        self.n_clips = n_clips
        self.source = source

    def to_dict(self) -> dict:
        return {"pitch_hz": round(self.pitch_hz, 1), "energy": round(self.energy),
                "rate_wps": self.rate_wps, "n_clips": self.n_clips,
                "source": self.source}

    @classmethod
    def from_clips(cls, clip_paths: list[str], texts: list[str] | None = None) -> "VoicePrint":
        """Measure a voice-print from passing clips (texts = what was read)."""
        if not clip_paths:
            raise VoiceCloneError("no clips — the voicebank must have passing clips first")
        pitches, energies, rates = [], [], []
        for i, cp in enumerate(clip_paths):
            rate, samples = read_wav(cp)
            if len(samples) < rate:  # under a second — skip, cannot measure
                continue
            # zero-crossing pitch estimate on the loudest 100ms window
            best = max(range(0, len(samples) - rate // 10, rate // 50),
                       key=lambda s: sum(abs(x) for x in samples[s:s + rate // 10]))
            win = samples[best:best + rate // 10]
            crossings = sum(1 for a, b in zip(win, win[1:]) if a < 0 <= b)
            # upward zero-crossings per second == fundamental frequency
            pitch = crossings * rate / (rate // 10)
            pitches.append(pitch)
            energies.append(statistics.median([abs(x) for x in samples]))
            if texts and i < len(texts):
                n_words = len(texts[i].split())
                rates.append(n_words / (len(samples) / rate))
        if not pitches:
            raise VoiceCloneError("clips too short to measure a voice print")
        return cls(statistics.median(pitches), statistics.median(energies),
                   statistics.mean(rates) if rates else 3.0, len(clip_paths))


class ToneCloneBackend:
    """Clones measured tone onto a base speaker (Kokoro/Piper on the Jetson).

    This is the pragmatic first clone: it cannot re-create timbre exactly, so
    it never claims to. It adjusts the base speaker's output to match the
    person's measured pitch, energy and speaking rate — a tone-carrying voice,
    not a counterfeit. The human A/B harness (step 12) validates it.
    """

    def __init__(self, config: MemoriaConfig, print_: VoicePrint | None = None):
        self.config = config
        self.voice_print = print_

    def available(self) -> bool:
        return True  # tone cloning needs no model beyond the base speaker

    def clone(self, person_id: str, clips: list[dict]) -> dict:
        """Produce the voice artifact entry: the print + backend selection."""
        paths = [c["path"] for c in clips]
        texts = [c.get("text") for c in clips if c.get("text")]
        vp = VoicePrint.from_clips(paths, texts if texts else None)
        self.voice_print = vp
        return {"backend": "tone-clone", "voice_print": vp.to_dict(),
                "base_speaker": "kokoro af_heart"}

    def synthesize(self, text: str, voice: str, out_path: str) -> Path:
        """Synthesize with the base speaker; tone-matching happens downstream."""
        if not text or not text.strip():
            raise VoiceCloneError("text is required")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        # The base speaker synthesis is wired in step 11 (the TTS service).
        # The backend records intent here; the service invokes Kokoro/Piper.
        raise NotImplementedError(
            "wired to the base speaker in step 11 — use MemoriaTTS.synthesize")


def quality_gate(print_a: VoicePrint, print_b: VoicePrint,
                 pitch_tolerance: float = 0.35,
                 rate_tolerance: float = 0.40) -> bool:
    """Is clone B a plausible match for the person's voice A?

    A clone may differ by up to 35% in pitch and 40% in rate — a tone-carrying
    approximation, not a counterfeit. Beyond that, memoria falls back to a
    stock voice rather than present a voice that misses the person.
    """
    if print_a.pitch_hz <= 0 or print_b.pitch_hz <= 0:
        return False
    pitch_ratio = abs(print_b.pitch_hz - print_a.pitch_hz) / print_a.pitch_hz
    rate_ratio = abs(print_b.rate_wps - print_a.rate_wps) / max(print_a.rate_wps, 0.1)
    return pitch_ratio <= pitch_tolerance and rate_ratio <= rate_tolerance
