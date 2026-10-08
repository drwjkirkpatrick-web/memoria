"""memoria.voicebank — collecting the person's voice, clip by clip.

The voicebank drives a person through a short guided reading script (chosen
for phoneme coverage), records each clip through any Recorder (mock or sox),
runs the step-4 quality gate on every clip, and keeps only what passes.
The voice-print the TTS backends train on is built from these clips.
"""
from __future__ import annotations
import uuid
from pathlib import Path

from .config import MemoriaConfig
from .interview import InterviewStore
from .models import VoiceSample
from .voice_capture import Recorder, analyze_clip

# Guided reading script: sentences chosen to cover common English phonemes —
# plosives, fricatives, vowels, diphthongs, and emotional range.
READING_SCRIPT = [
    "The quick brown fox jumps over the lazy dog.",
    "She sells sea shells by the sea shore, and the shells shine silver.",
    "Twenty tiny turtles tumbled toward the tall timber together.",
    "How much wood would a woodchuck chuck if a woodchuck could chuck wood?",
    "I remember the kitchen in the morning, coffee warming on the stove.",
    "Yes, of course, we can do that. No, thank you, not today.",
    "Whisper this softly, then say it with a laugh: what a wonderful life.",
    "Ruth threw three red roses by the riverside road.",
    "Measure the pleasure of leisure on a treasure hunt through the weather.",
    "Good morning, my love. I hope you slept well. Come here, sit with me.",
]


class VoicebankError(Exception):
    pass


class Voicebank:
    """Collects voice clips for one person, with the quality gate enforced."""

    MIN_PASS_CLIPS = 5   # a voice-print needs at least 5 good clips

    def __init__(self, config: MemoriaConfig, recorder: Recorder):
        self.config = config
        self.store = InterviewStore(config)
        self.recorder = recorder

    def _require_person(self, person_id: str) -> None:
        self.store.get_person(person_id)

    def _clip_dir(self, person_id: str) -> Path:
        d = Path(self.config.person_dir(person_id)) / "voice"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def record_script_line(self, person_id: str, line_index: int,
                           seconds: float = 8.0) -> dict:
        """Record one line of the reading script. Returns the clip report."""
        self._require_person(person_id)
        if not 0 <= line_index < len(READING_SCRIPT):
            raise VoicebankError(f"script line {line_index} out of range "
                                 f"(0..{len(READING_SCRIPT)-1})")
        clip_id = f"vs_{uuid.uuid4().hex[:12]}"
        path = self._clip_dir(person_id) / f"{clip_id}.wav"
        self.recorder.record(seconds, path)
        report = analyze_clip(path)
        sample = VoiceSample(id=clip_id, person_id=person_id, path=str(path),
                             duration_s=report["duration_s"],
                             quality_report=report)
        self.store.add_voice_sample(sample)
        return {"clip_id": clip_id, "line": READING_SCRIPT[line_index],
                "path": str(path), "report": report,
                "accepted": report["verdict"] == "pass"}

    def report(self, person_id: str) -> dict:
        """The voicebank status: every clip's verdict, and readiness."""
        self._require_person(person_id)
        samples = self.store.voice_samples(person_id)
        verdicts = [s.quality_report.get("verdict", "fail") for s in samples]
        passes = sum(1 for v in verdicts if v == "pass")
        return {"clips": len(samples),
                "pass": passes,
                "warn": sum(1 for v in verdicts if v == "warn"),
                "fail": sum(1 for v in verdicts if v == "fail"),
                "ready": passes >= self.MIN_PASS_CLIPS,
                "total_duration_s": round(sum(s.duration_s for s in samples), 1),
                "script_lines": len(READING_SCRIPT)}

    def ready_clips(self, person_id: str) -> list[dict]:
        """Only the clips that passed the gate — the TTS training set."""
        out = []
        for s in self.store.voice_samples(person_id):
            if s.quality_report.get("verdict") == "pass":
                out.append({"clip_id": s.id, "path": s.path,
                            "duration_s": s.duration_s})
        return out
