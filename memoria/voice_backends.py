"""memoria.voice_backends — pluggable TTS backends, config-driven.

Backends implement the VoiceBackend contract (synthesize). Registry order and
availability are config-driven, so a Jetson with NeuTTS Air accepted on HF can
use it, while a machine without access degrades cleanly to Kokoro/Piper.

NeuTTS Air adds zero-shot voice CLONING from ~10s of reference audio —
a real timbre clone, not just tone matching. It is HF-gated; the backend
reports `unavailable` with the exact reason until access + token exist.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Protocol

from .config import MemoriaConfig


class BackendError(Exception):
    pass


class VoiceBackend(Protocol):
    name: str
    def available(self) -> tuple[bool, str]: ...
    def synthesize(self, text: str, voice_ref: str | None, out_path: str) -> Path: ...


class KokoroBackend:
    """Kokoro-82M, installed and proven on the Jetson (CPU, ~1x RT)."""
    name = "kokoro"

    def __init__(self, config: MemoriaConfig):
        self.config = config

    def available(self) -> tuple[bool, str]:
        try:
            import kokoro  # noqa
            return (True, "")
        except ImportError:
            return (False, "pip install kokoro soundfile")

    def synthesize(self, text: str, voice_ref: str | None, out_path: str) -> Path:
        ok, why = self.available()
        if not ok:
            raise BackendError(f"kokoro unavailable: {why}")
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        from kokoro import KPipeline
        if not hasattr(self, "_pipe"):
            self._pipe = KPipeline(lang_code="a", device="cpu")
        results = list(self._pipe(text, voice=voice_ref or "af_heart"))
        if not results:
            raise BackendError("kokoro produced no audio")
        import numpy as np
        audio = np.concatenate([r.audio for r in results])
        import soundfile as sf
        sf.write(out_path, audio, 24000)
        return Path(out_path)


class NeuTTSBackend:
    """NeuTTS Air — zero-shot voice cloning; HF-gated (auto-approve).

    Requires: HF_TOKEN + accepted terms at huggingface.co/neuphonic/neutts-air.
    Until then available() returns (False, reason) and the registry falls back.
    """
    name = "neutts"

    def __init__(self, config: MemoriaConfig, backbone: str = "neuphonic/neutts-air",
                 codec: str = "neuphonic/neucodec"):
        self.config = config
        self.backbone = backbone
        self.codec = codec

    def available(self) -> tuple[bool, str]:
        try:
            import neutts  # noqa
        except ImportError:
            return (False, "pip install neutts")
        if not (os.environ.get("HF_TOKEN") or Path("~/.huggingface/token").expanduser().is_file()):
            return (False, "HF_TOKEN not set — NeuTTS Air is gated")
        # quick reachability probe without loading weights
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            api.model_info(self.backbone)
            return (True, "")
        except Exception as e:
            msg = str(e)
            if "401" in msg or "gated" in msg.lower() or "access" in msg.lower():
                return (False, "gated repo not accessible — accept terms at "
                               "huggingface.co/neuphonic/neutts-air and set HF_TOKEN")
            return (False, f"hub error: {msg[:120]}")

    def synthesize(self, text: str, voice_ref: str | None, out_path: str) -> Path:
        ok, why = self.available()
        if not ok:
            raise BackendError(f"neutts unavailable: {why}")
        from neutts import NeuTTS
        tts = NeuTTS(backbone_repo=self.backbone, codec_repo=self.codec,
                     backbone_device="cpu", codec_device="cpu")
        audio = tts.infer(text, audio_prompt=voice_ref) if voice_ref else tts.infer(text)
        import soundfile as sf
        # NeuTTS returns a tensor; 24kHz
        data = audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio
        sf.write(out_path, data, 24000)
        return Path(out_path)


class PiperBackend:
    """Piper — fastest stock-voice fallback (~1400x RT)."""
    name = "piper"

    def __init__(self, config: MemoriaConfig, voice_dir: str | None = None):
        self.config = config
        self.voice_dir = Path(voice_dir or (Path.home() / "models" / "piper-voices"))

    def available(self) -> tuple[bool, str]:
        try:
            import piper  # noqa
            if not any(self.voice_dir.glob("*.onnx")):
                return (False, f"no voices in {self.voice_dir}")
            return (True, "")
        except ImportError:
            return (False, "pip install piper-tts")

    def synthesize(self, text: str, voice_ref: str | None, out_path: str) -> Path:
        ok, why = self.available()
        if not ok:
            raise BackendError(f"piper unavailable: {why}")
        import subprocess, sys, tempfile
        model = next(self.voice_dir.glob("*.onnx"))
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tmp_out = tf.name
        r = subprocess.run([sys.executable, "-m", "piper", "--model", str(model),
                            "--output_file", tmp_out],
                           input=text.encode(), capture_output=True, timeout=180)
        if r.returncode != 0:
            raise BackendError("piper synthesis failed")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(Path(tmp_out).read_bytes())
        Path(tmp_out).unlink(missing_ok=True)
        return out


# --- registry --------------------------------------------------------------

def build_registry(config: MemoriaConfig, order: list[str] | None = None):
    """Config-driven backend chain. Default order: neutts (clone) > kokoro > piper."""
    classes = {"neutts": NeuTTSBackend, "kokoro": KokoroBackend, "piper": PiperBackend}
    order = order or ["neutts", "kokoro", "piper"]
    chain = []
    for name in order:
        if name not in classes:
            raise BackendError(f"unknown backend: {name!r}")
        chain.append(classes[name](config))
    return chain


def first_available(config: MemoriaConfig, order: list[str] | None = None):
    """The first backend whose available() is True, plus the reasons the others gave."""
    reasons = []
    for b in build_registry(config, order):
        ok, why = b.available()
        if ok:
            return b, reasons
        reasons.append(f"{b.name}: {why}")
    return None, reasons
