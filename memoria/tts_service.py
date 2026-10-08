"""memoria.tts_service — the voice of the memorial, as a local service.

FastAPI on :8092. Endpoints:
  POST /synthesize   {person_id, text, voice?} -> audio/wav
  GET  /voices       available voices (stock + cloned)
  GET  /health

Privacy: no text or audio is retained after synthesis; no logs of content;
audio is cached by hash ONLY while the service runs (memory cache), never on disk.
"""
from __future__ import annotations
import hashlib
import io
import sys
import wave
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .config import load_config
from .interview import InterviewStore

app = FastAPI(title="memoria TTS", version="0.1.0")

# --- engines -------------------------------------------------------------

KOKORO_AVAILABLE = None   # resolved lazily; both engines are optional
PIPER_AVAILABLE = None
_engine = None
_engine_kind = None


class _KokoroEngine:
    """Kokoro-82M via the installed kokoro package (CPU on the Jetson)."""

    def __init__(self):
        import os
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        from kokoro import KPipeline
        self.pipeline = KPipeline(lang_code="a", device="cpu")
        self.rate = 24000

    def synth(self, text: str, voice: str) -> bytes:
        results = list(self.pipeline(text, voice=voice))
        if not results:
            raise HTTPException(400, "synthesis produced no audio")
        import numpy as np
        audio = np.concatenate([r.audio for r in results])
        return _wav_bytes(audio, self.rate)


class _PiperEngine:
    """Piper via the installed piper-tts package (fast fallback)."""

    def __init__(self):
        import piper
        self.piper = piper
        self.voice_dir = Path.home() / "models" / "piper-voices"
        self.voice = "en_US-amy-medium"
        self.rate = 22050

    def synth(self, text: str, voice: str) -> bytes:
        import subprocess, tempfile, os
        model = self.voice_dir / f"{voice or self.voice}.onnx"
        if not model.is_file():
            raise HTTPException(400, f"unknown voice {voice!r}")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            out = tf.name
        r = subprocess.run([sys.executable, "-m", "piper", "--model", str(model),
                            "--output_file", out],
                           input=text.encode(), capture_output=True, timeout=120)
        if r.returncode != 0:
            raise HTTPException(500, "piper failed")
        data = Path(out).read_bytes()
        Path(out).unlink(missing_ok=True)
        return data


def _wav_bytes(samples, rate: int) -> bytes:
    import numpy as np
    if samples.dtype != np.int16:
        samples = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def get_engine():
    """Prefer Kokoro (quality); fall back to Piper (speed); else unavailable."""
    global _engine, _engine_kind
    if _engine is not None:
        return _engine, _engine_kind
    try:
        _engine = _KokoroEngine()
        _engine_kind = "kokoro"
    except Exception:
        try:
            _engine = _PiperEngine()
            _engine_kind = "piper"
        except Exception:
            _engine, _engine_kind = None, None
    return _engine, _engine_kind


# --- models --------------------------------------------------------------

class SynthesizeRequest(BaseModel):
    person_id: str
    text: str
    voice: str | None = None


class VoiceInfo(BaseModel):
    id: str
    label: str
    kind: str  # stock | cloned


# --- cache (memory only, never disk) -------------------------------------

_cache: dict[str, bytes] = {}
_CACHE_LIMIT = 64


def _cache_key(person_id: str, text: str, voice: str | None) -> str:
    return hashlib.sha256(f"{person_id}|{text}|{voice}".encode()).hexdigest()[:24]


# --- endpoints -----------------------------------------------------------

@app.get("/health")
def health():
    engine, kind = get_engine()
    return {"ok": True, "engine": kind, "engine_up": engine is not None}


@app.get("/voices")
def voices():
    engine, kind = get_engine()
    stock = []
    if kind == "kokoro":
        stock = [VoiceInfo(id="af_heart", label="Heart (female, stock)", kind="stock"),
                 VoiceInfo(id="am_michael", label="Michael (male, stock)", kind="stock"),
                 VoiceInfo(id="bf_emma", label="Emma (British, stock)", kind="stock")]
    elif kind == "piper":
        stock = [VoiceInfo(id="en_US-amy-medium", label="Amy (stock)", kind="stock")]
    store = InterviewStore(load_config())
    cloned = []
    for person in store.list_people():
        # a cloned voice exists when the person has a voice-print artifact
        vdir = Path(load_config().person_dir(person.id)) / "voice"
        vprint = vdir / "voice-print.json"
        if vprint.is_file():
            cloned.append(VoiceInfo(id=person.id, label=f"{person.name} (cloned)", kind="cloned"))
    return {"engine": kind, "voices": stock + cloned}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    engine, kind = get_engine()
    if engine is None:
        raise HTTPException(503, "no TTS engine available")
    if not req.text.strip():
        raise HTTPException(400, "text is required")
    cfg = load_config()
    try:
        store = InterviewStore(cfg)
        store.get_person(req.person_id)   # person must exist
    except Exception:
        raise HTTPException(404, "person not found")
    voice = req.voice or ("af_heart" if kind == "kokoro" else "en_US-amy-medium")
    key = _cache_key(req.person_id, req.text, voice)
    if key in _cache:
        return Response(_cache[key], media_type="audio/wav")
    data = engine.synth(req.text, voice)
    if len(_cache) >= _CACHE_LIMIT:
        _cache.pop(next(iter(_cache)))  # simple FIFO
    _cache[key] = data
    return Response(data, media_type="audio/wav")
