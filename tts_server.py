"""Ria's own voice server: the OmniVoice engine run directly with the owner's reference voice (no VoiceStudio around it).
Same engine, same reference audio and text, same settings as the VoiceStudio profile "My voice clean hi" - but faster and with less GPU memory.
Same endpoints as VoiceStudio, so Ria only needs VOICESTUDIO_URL=http://localhost:3901.
Run with VoiceStudio's Python:   <VoiceStudio python> tts_server.py     (see tts_start.bat)"""
import io
import os
import subprocess
import sys
import threading

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT = os.environ.get("OMNIVOICE_CHECKPOINT", r"D:\voice studio\models--k2-fsa--OmniVoice\snapshots\c5fdb5ccb189668d56333f77ba2629f4cd7535f4")
REF_AUDIO = os.environ.get("RIA_REF_AUDIO", os.path.join(HERE, "voice_ref", "ria_ref.wav"))
REF_TEXT = open(os.environ.get("RIA_REF_TEXT", os.path.join(HERE, "voice_ref", "ria_ref.txt")), encoding="utf-8").read().strip()
PORT = int(os.environ.get("TTS_PORT", "3901"))
DEFAULT_STEPS = int(os.environ.get("TTS_STEPS", "24"))
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

from omnivoice.models.omnivoice import OmniVoice  # noqa: E402
from omnivoice.utils.dtype import tts_dtype_name  # noqa: E402

print("loading OmniVoice ...", flush=True)
model = OmniVoice.from_pretrained(CHECKPOINT, device_map="cuda", dtype=getattr(torch, tts_dtype_name("cuda")))
PROMPT = model.create_voice_clone_prompt(ref_audio=REF_AUDIO, ref_text=REF_TEXT)       # the voice, prepared once
LOCK = threading.Lock()
SR = int(getattr(model, "sampling_rate", 24000))
torch.cuda.empty_cache()
print("ready", flush=True)
app = FastAPI()


def synth(text: str, speed: float, steps: int, language: str = "hi") -> np.ndarray:
    with LOCK:
        try:
            audios = model.generate(text=text, language=language or "hi", voice_clone_prompt=PROMPT, num_step=steps, speed=speed)
            a = audios[0] if isinstance(audios, (list, tuple)) else audios
            return a.detach().to("cpu").float().numpy().squeeze()
        finally:
            torch.cuda.empty_cache()          # give unused GPU memory back after every sentence: it grew to 6-7 GB of 8 and made sentences take minutes


def encode(x: np.ndarray, fmt: str) -> tuple:
    buf = io.BytesIO()
    sf.write(buf, x, SR, format="WAV", subtype="PCM_16")
    wav = buf.getvalue()
    if fmt == "mp3":
        r = subprocess.run([FFMPEG, "-loglevel", "error", "-i", "pipe:0", "-codec:a", "libmp3lame", "-b:a", "96k", "-f", "mp3", "pipe:1"], input=wav, capture_output=True)
        if r.returncode == 0 and r.stdout:
            return r.stdout, "audio/mpeg"
    return wav, "audio/wav"


@app.get("/health")
def health():
    return {"ok": True, "engine": "omnivoice", "voice": "ria"}


@app.get("/v1/audio/voices")
def voices():
    return {"voices": [{"id": "ria", "name": "Ria"}]}


@app.get("/profiles")
def profiles():
    return [{"id": "ria", "name": "Ria"}]


@app.post("/system/flush-memory")
def flush():
    torch.cuda.empty_cache()
    return {"flushed": True}


@app.post("/generate")
def generate(text: str = Form(...), language: str = Form("hi"), speed: str = Form("1.0"), num_step: str = Form("0")):
    x = synth(text, float(speed or 1.0), int(num_step or 0) or DEFAULT_STEPS, language)
    body, _ = encode(x, "wav")
    return Response(body, media_type="audio/wav")


class Speech(BaseModel):
    input: str
    language: str = "hi"
    speed: float = 1.0
    response_format: str = "wav"
    num_step: int = 0
    model: str = ""
    voice: str = ""


@app.post("/v1/audio/speech")
def speech(r: Speech):
    x = synth(r.input, r.speed or 1.0, r.num_step or DEFAULT_STEPS, r.language)
    body, mime = encode(x, r.response_format)
    return Response(body, media_type=mime)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
