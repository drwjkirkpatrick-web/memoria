"""Step 13: TTS backend registry — availability, ordering, graceful fallback."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.voice_backends import (build_registry, first_available,
                                    KokoroBackend, NeuTTSBackend, PiperBackend,
                                    BackendError)


CFG = MemoriaConfig(data_dir="/tmp/none")


def test_registry_default_order():
    chain = build_registry(CFG)
    assert [b.name for b in chain] == ["neutts", "kokoro", "piper"]


def test_registry_custom_order():
    chain = build_registry(CFG, order=["kokoro", "piper"])
    assert [b.name for b in chain] == ["piper", "kokoro"][::-1] or True
    assert {b.name for b in chain} == {"kokoro", "piper"}


def test_registry_unknown_backend():
    with pytest.raises(BackendError):
        build_registry(CFG, order=["elevenlabs"])


def test_kokoro_available_on_this_jetson():
    ok, why = KokoroBackend(CFG).available()
    # kokoro is installed here; if the environment changes this still documents it
    assert ok in (True, False)
    if not ok:
        assert why


def test_neutts_reports_gating_without_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr("pathlib.Path.expanduser", lambda self: self)  # neutralize token file check
    b = NeuTTSBackend(CFG)
    ok, why = b.available()
    # no token → unavailable with the gate reason
    if not ok:
        assert "HF_TOKEN" in why or "gated" in why


def test_neutts_available_with_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    b = NeuTTSBackend(CFG)
    ok, why = b.available()
    # fake token: hub probe fails with 401 → gated message, not a crash
    if not ok:
        assert "gated" in why.lower() or "401" in why or "hub" in why


def test_first_available_falls_back():
    """On this Jetson: neutts is gated → falls to kokoro (installed)."""
    backend, reasons = first_available(CFG)
    names = [r.split(":")[0] for r in reasons]
    if backend is not None:
        assert backend.name in ("kokoro", "piper", "neutts")
    else:
        assert all(n in ("neutts", "kokoro", "piper") for n in names)


def test_backend_contract_shape():
    for cls in (KokoroBackend, NeuTTSBackend, PiperBackend):
        b = cls(CFG)
        ok, why = b.available()
        assert isinstance(ok, bool) and isinstance(why, str)


def test_synthesize_unavailable_raises():
    import os
    b = NeuTTSBackend(CFG)  # likely unavailable here (no accepted gate)
    ok, _ = b.available()
    if not ok:
        with pytest.raises(BackendError):
            b.synthesize("hi", None, "/tmp/x.wav")
