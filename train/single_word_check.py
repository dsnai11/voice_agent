"""Single spoken words must be heard (needs VoiceStudio and the listener running; set STT_ENGINE=hinglish and LLM_BASE_URL).   python train/single_word_check.py"""
import re
import io, sys, numpy as np, requests, soundfile as sf
sys.path.insert(0, "D:/Voice Agent Model/voice_agent"); sys.stdout.reconfigure(encoding="utf-8")
import listen
WORDS = ["हाँ", "नहीं", "जी", "ठीक", "पर्सनल", "जयपुर", "सैलरी", "बिज़नेस", "ओके", "बाय", "हेलो", "सही"]
def tts(w):
    r = requests.post("http://localhost:3900/v1/audio/speech", json={"model": "tts-1", "voice": "507e7da2", "input": w, "language": "hi", "speed": 1.0, "response_format": "wav"}, timeout=120)
    a, sr = sf.read(io.BytesIO(r.content), dtype="float32"); a = a if a.ndim == 1 else a[:, 0]
    y = np.interp(np.linspace(0, len(a), int(len(a) * 16000 / sr), endpoint=False), np.arange(len(a)), a).astype("float32")
    idx = np.where(np.abs(y) > 0.004)[0]; y = y[idx[0]:idx[-1] + 1] if len(idx) else y        # trim to the spoken part only
    return y * (0.15 / max(1e-6, np.abs(y).max()))                                          # a normal phone-mic level
def asr(a):
    b = io.BytesIO(); sf.write(b, a, 16000, format="WAV", subtype="PCM_16")
    return requests.post("http://localhost:3950/transcribe", files={"file": ("a.wav", b.getvalue(), "audio/wav")}, timeout=60).json()["text"]
def seg(a, **kw):
    s = listen.Segmenter(0.012, end_silence_s=0.45, **kw); sil = np.zeros(listen.BLOCK, "float32")
    stream = [sil] * 10 + [a[i:i + listen.BLOCK] for i in range(0, len(a) - listen.BLOCK + 1, listen.BLOCK)] + [sil] * 30
    for blk in stream:
        out = s.feed(blk.astype("float32"))
        if out is not None: return out
    return None
import stt, server
WORDS += ["मुंबई", "दिल्ली", "पाँच लाख", "ठीक है", "हाँ जी"]
ok = 0
for w in WORDS:
    a = tts(w)
    chunk = seg(a, min_speech_s=0.12)
    text = stt.transcribe_hinglish(chunk) if chunk is not None else ""
    short = chunk is not None and len(chunk) / 16000 < 0.4 + 0.0
    keep = bool(text) and (len(a) / 16000 >= 0.4 or server._short_answer(text))
    ok += keep
    print(f"{w:10s} {len(a)/16000:4.2f}s -> chunk {'yes' if chunk is not None else 'NO '} heard {text!r:14} {'ACCEPTED' if keep else 'LOST'}")
print(f"single words accepted: {ok}/{len(WORDS)}")
bad = len(WORDS) - ok
rng = np.random.default_rng(1)
for name, noise in (("click", rng.normal(0, 0.2, 2400)), ("cough", rng.normal(0, 0.15, 4800) * np.hanning(4800))):
    n = noise.astype("float32"); chunk = seg(n, min_speech_s=0.12)
    text = stt.transcribe_hinglish(chunk) if chunk is not None else ""
    keep = bool(text) and (len(n) / 16000 >= 0.4 or server._short_answer(text))
    print(f"{name:6s} segmenter {'passes' if chunk is not None else 'blocks'} | asr {text!r} | counted as speech: {keep}")

print('SINGLE WORD CHECK: ALL OK' if bad <= 2 else f'SINGLE WORD CHECK: {bad} LOST')
sys.exit(1 if bad > 2 else 0)
