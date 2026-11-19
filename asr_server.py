"""Hinglish listening service for Ria (local, GPU).

Runs Oriserve/Whisper-Hindi2Hinglish-Apex (a Whisper model fine-tuned on noisy Indian speech) and returns what the caller
said in Roman-letter Hinglish ("mera naam Gaurav Sharma hai"). Ria's reply bank, language model and form all read Roman
Hinglish well, unlike the Urdu-script text the stock Whisper often writes for Hindi.

Run (uses VoiceStudio's Python, which already has PyTorch + CUDA + transformers):
    asr_start.bat          or
    <VoiceStudio python> asr_server.py

POST /transcribe   multipart file=<wav, 16 kHz mono>   ->   {"text": "...", "seconds": 0.4}
GET  /health
"""
import io
import os
import time

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, File, UploadFile
from transformers import pipeline

MODEL = os.environ.get("ASR_MODEL_DIR", r"D:/asr_models/Whisper-Hindi2Hinglish-Apex")
PORT = int(os.environ.get("ASR_PORT", "3950"))
LANGUAGE = os.environ.get("ASR_LANGUAGE", "hi")             # "hi": the model writes Hinglish in Roman letters; try "en" if English-only callers dominate
TARGET_PEAK = float(os.environ.get("ASR_TARGET_PEAK", "0.7"))   # quiet microphones are boosted to this peak before listening

device = "cuda:0" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if torch.cuda.is_available() else torch.float32
print(f"loading {MODEL} on {device} ...", flush=True)
pipe = pipeline("automatic-speech-recognition", model=MODEL, torch_dtype=dtype, device=device)
pipe({"raw": np.zeros(16000, dtype="float32"), "sampling_rate": 16000}, generate_kwargs={"task": "transcribe", "language": LANGUAGE})   # warm-up
print("ready", flush=True)

app = FastAPI()


def boost(a: np.ndarray) -> np.ndarray:
    peak = float(np.abs(a).max()) if a.size else 0.0
    if peak < 1e-4:
        return a
    gain = min(TARGET_PEAK / peak, 30.0)                      # never amplify more than 30x
    return (a * gain).astype("float32")


@app.get("/health")
def health():
    return {"ok": True, "model": os.path.basename(MODEL), "device": device, "language": LANGUAGE}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    t = time.time()
    audio, rate = sf.read(io.BytesIO(await file.read()), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    out = pipe({"raw": boost(audio), "sampling_rate": rate}, generate_kwargs={"task": "transcribe", "language": LANGUAGE})
    return {"text": (out.get("text") or "").strip(), "seconds": round(time.time() - t, 2)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
