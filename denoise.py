"""Noise removal applied to the caller's audio before it is sent to the listener (Gemini).

Engines (set DENOISE=...):
  none      - leave the audio as it is
  rnnoise   - RNNoise, a small neural denoiser; copes with changing noise such as traffic and voices
  spectral  - noisereduce spectral filtering; good for steady hiss and hum, weaker on changing noise
Any failure falls back to the original audio, so noise removal can never break a call.
"""
import os

import numpy as np

RATE = 16000
ENGINE = os.environ.get("DENOISE", "none").lower()


def _rnnoise(audio: np.ndarray) -> np.ndarray:
    from pyrnnoise import RNNoise

    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("int16")[None, :]
    frames = [frame for _prob, frame in RNNoise(sample_rate=RATE).denoise_chunk(pcm, partial=False)]
    out = np.concatenate(frames, axis=1)[0].astype("float32") / 32768.0
    return out


def _spectral(audio: np.ndarray) -> np.ndarray:
    import noisereduce as nr

    return nr.reduce_noise(y=audio, sr=RATE, stationary=False).astype("float32")


ENGINES = {"rnnoise": _rnnoise, "spectral": _spectral}


def clean(audio: np.ndarray, engine: str = "") -> np.ndarray:
    """Return the audio with background noise reduced (16 kHz mono float32), or unchanged if disabled or failing."""
    fn = ENGINES.get((engine or ENGINE).lower())
    if fn is None or audio.size == 0:
        return audio
    try:
        out = fn(audio.astype("float32"))
        return out if out.size else audio
    except Exception as e:           # never let a denoiser problem break a call
        print(f"denoise failed ({type(e).__name__}); using original audio", flush=True)
        return audio
