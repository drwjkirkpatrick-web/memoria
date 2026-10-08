"""memoria.voice_verify — does the clone sound like the person?

A/B harness comparing original clips against synthesized audio:

- spectral statistics (centroid, rolloff, flatness — stdlib numpy-free approximations)
- rate comparison (words per second)
- an auto-verdict from those numbers
- a human MOS checklist FILE — because the real quality gate is human ears

The harness never claims the clone is the person; it measures how close the
tone-carrying approximation lands.
"""
from __future__ import annotations
import math
import statistics
from pathlib import Path

from .voice_capture import read_wav


class VerifyError(Exception):
    pass


def _spectral_stats(samples: list[int], rate: int) -> dict:
    """Cheap spectral sketch via zero-crossing density as a brightness proxy.

    True spectral stats need FFT; numpy lives on the Jetson but the harness
    stays import-light so tests and the visitor page can run anywhere.
    Brightness = zero-crossings per second — higher = brighter/hissier.
    """
    if len(samples) < 2:
        raise VerifyError("clip too short to analyze")
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b)
    brightness = crossings / (len(samples) / rate)
    abs_amps = [abs(s) for s in samples[:: max(1, len(samples) // 8000)]]  # subsample
    energy = statistics.median(abs_amps)
    # flatness proxy: ratio of quiet frames to loud frames
    loud = sum(1 for a in abs_amps if a > energy * 2)
    quiet = sum(1 for a in abs_amps if a < energy * 0.5)
    n = max(1, len(abs_amps))
    return {"brightness": round(brightness, 1), "energy": round(energy),
            "flatness": round((quiet + 0.0) / n, 3), "loud_ratio": round(loud / n, 3)}


def _rate_wps(text: str, duration_s: float) -> float:
    if duration_s <= 0:
        raise VerifyError("duration must be positive")
    return len(text.split()) / duration_s


def compare_pair(original_path: str, synthesized_path: str,
                 original_text: str, synthesized_text: str) -> dict:
    """One A/B pair: stats for both sides and the deltas."""
    r1, s1 = read_wav(original_path)
    r2, s2 = read_wav(synthesized_path)
    a = _spectral_stats(s1, r1)
    b = _spectral_stats(s2, r2)
    dur1, dur2 = len(s1) / r1, len(s2) / r2
    rate1 = _rate_wps(original_text, dur1)
    rate2 = _rate_wps(synthesized_text, dur2)
    return {
        "original": {"path": str(original_path), "duration_s": round(dur1, 2),
                     "rate_wps": round(rate1, 2), **a},
        "synthesized": {"path": str(synthesized_path), "duration_s": round(dur2, 2),
                        "rate_wps": round(rate2, 2), **b},
        "deltas": {
            "brightness_ratio": round(b["brightness"] / max(a["brightness"], 1e-6), 3),
            "energy_ratio": round(b["energy"] / max(a["energy"], 1e-6), 3),
            "rate_ratio": round(rate2 / max(rate1, 1e-6), 3),
            "duration_ratio": round(dur2 / max(dur1, 1e-6), 3),
        },
    }


def auto_verdict(pair: dict, brightness_tol: float = 0.6,
                 rate_tol: float = 0.5) -> str:
    """Machine pre-check from deltas: close / review / investigate."""
    d = pair["deltas"]
    b_ok = 1 - brightness_tol <= d["brightness_ratio"] <= 1 + brightness_tol
    r_ok = 1 - rate_tol <= d["rate_ratio"] <= 1 + rate_tol
    if b_ok and r_ok:
        return "close"
    if b_ok or r_ok:
        return "review"
    return "investigate"


def mos_checklist(pairs: list[dict]) -> str:
    """The human MOS checklist as a Markdown file. Human ears are the gate."""
    lines = ["# Voice verification — human listening checklist", "",
             "Listen to each pair A (original) then B (synthesized).",
             "Score each 1-5. The clone is accepted only with a mean MOS >= 3.5.", ""]
    for i, p in enumerate(pairs, 1):
        a_path = p["original"]["path"]
        b_path = p["synthesized"]["path"]
        verdict = auto_verdict(p)
        lines += [f"## Pair {i}",
                  f"- A (original): `{a_path}`",
                  f"- B (synthesized): `{b_path}`",
                  f"- machine pre-check: {verdict}",
                  "",
                  "| Aspect | 1 | 2 | 3 | 4 | 5 |",
                  "|---|---|---|---|---|---|",
                  "| Sounds like them (tone) | | | | | |",
                  "| Natural, not robotic | | | | | |",
                  "| Comfortable to listen to | | | | | |",
                  "| Would recognize in a blind test | | | | | |",
                  ""]
    lines += ["## Verdict",
              "",
              "- Mean MOS: ______",
              "- Accepted (MOS >= 3.5): yes / no",
              "- Listener: ____________  Date: ____________", ""]
    return "\n".join(lines)


def verify_voice(originals: list[dict], synthesized: list[dict]) -> dict:
    """Full report: pairs, machine pre-checks, and the checklist content.

    originals / synthesized: [{path, text}]
    """
    if len(originals) != len(synthesized):
        raise VerifyError("same number of originals and synthesized clips required")
    if not originals:
        raise VerifyError("no pairs to verify")
    pairs = []
    for o, s in zip(originals, synthesized):
        p = compare_pair(o["path"], s["path"], o.get("text", ""), s.get("text", ""))
        p["machine_verdict"] = auto_verdict(p)
        pairs.append(p)
    verdicts = [p["machine_verdict"] for p in pairs]
    return {"pairs": pairs,
            "machine_verdicts": verdicts,
            "all_close": all(v == "close" for v in verdicts),
            "checklist_markdown": mos_checklist(pairs)}
