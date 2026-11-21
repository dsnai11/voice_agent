"""Speech-to-text for the web app.

Gemini listens to the caller's audio: much more accurate than Whisper-small for Hindi, Hinglish and spoken numbers.
Whisper (local) is kept as a fallback if the Gemini call fails.
Privacy: with STT_ENGINE=gemini the caller's audio is sent to Google. Use the paid plan for real customer data.
"""
import base64
import io
import os
import time

import numpy as np
import soundfile as sf
from openai import RateLimitError

import brain

STT_LLM_MODEL = os.environ.get("STT_LLM_MODEL", brain.LLM_MODEL)

PROMPT = (
    "You are the speech recognizer for a phone call to an Indian finance company. "
    "Transcribe exactly what the caller says. The caller speaks Hindi, English or a mix (Hinglish). "
    "Write Hindi words in Devanagari and English words in Roman letters, as spoken. "
    "Write phone numbers, account numbers and amounts as digits (for example 9876543210). "
    "Likely words: loan, EMI, account number, payment, personal loan, home loan, business loan, vehicle loan, gold loan, "
    "complaint, callback, Jaipur, Delhi, Mumbai, lakh, thousand. "
    "Output ONLY the transcript, nothing else. "
    "If you cannot clearly hear speech, output exactly [silence]. Never guess or invent words."
)


# Words the listener should expect: nudges Whisper's spelling of numbers, loan terms and cities (STT_HINT in the environment overrides it)
API_HINT = os.environ.get("STT_HINT", "लोन, पर्सनल लोन, होम लोन, बिज़नेस लोन, गोल्ड लोन, ईएमआई, लोन अकाउंट नंबर, फ़ोन नंबर नौ आठ सात छह पाँच चार तीन दो एक शून्य, "
                                      "पाँच लाख रुपये, पचास हज़ार, जयपुर, दिल्ली, मुंबई, कॉलबैक, शिकायत।")


ASR_URL = os.environ.get("ASR_URL", "http://127.0.0.1:3950")


def transcribe_hinglish(audio: np.ndarray, rate: int = 16000) -> str:
    """Listen with the local Hinglish model (asr_server.py): the caller's own words in Roman letters, no hint prompt, quiet audio boosted."""
    import requests

    if len(audio) < rate * 1.5:                                  # a single word is heard much better with a little silence around it
        pad = np.zeros(int(rate * 0.5), dtype=audio.dtype)
        audio = np.concatenate([pad, audio, pad])
    buf = io.BytesIO()
    sf.write(buf, audio, rate, format="WAV", subtype="PCM_16")
    r = requests.post(ASR_URL.rstrip("/") + "/transcribe", files={"file": ("audio.wav", buf.getvalue(), "audio/wav")}, timeout=60)
    r.raise_for_status()
    text = fix_terms((r.json().get("text") or "").strip())
    if text.lower().strip(" .!?,") in _PHANTOM:
        return ""
    return _drop_loops(text)


def _drop_loops(text: str) -> str:
    """The recogniser sometimes loops on noise or a very short sound ("जा जा जा जा ..."): a word repeated 4+ times in a row is never real speech."""
    words = text.split()
    run, best = 1, 1
    for i in range(1, len(words)):
        run = run + 1 if words[i].strip(".,!?") == words[i - 1].strip(".,!?") else 1
        best = max(best, run)
    if best < 4:
        return text
    kept = []
    for w in words:
        if kept and w.strip(".,!?") == kept[-1].strip(".,!?"):
            continue
        kept.append(w)
    return "" if len(kept) <= 1 and len(words) >= 6 else " ".join(kept)


# Business words this model is known to mishear (it was not trained on loan vocabulary). Only exact, unambiguous slips are fixed here.
_TERM_FIXES = [
    (r"\bp\.?\s?d\.?\s+loan\b|\bpaid\s+loan\b|\bpede\s+loan\b", "payday loan"),
    (r"\bpay\s*-?\s*day\s+(?:loan|lone|launch|lan|loon)\b", "payday loan"),
    (r"\bpay\s*-?\s*day\b", "payday"),
    (r"\bsalary\s+(?:lone|launch|loon)\b", "salary loan"),
    (r"\bpersonal\s+(?:lone|launch|loon)\b", "personal loan"),
    (r"\b(?:e\.?\s?m\.?\s?i\.?|emmi|aimi)\b", "EMI"),
    (r"\bsibil\b|\bcibil\b|\bcivil\s+score\b", "CIBIL"),
]


_PHANTOM = {"nan", "none", "null", "[silence]", "you", "thanks for watching", "thank you for watching", "subscribe", "music", "mm", "hmm", "uh", "um", "subtitles by the amara.org community"}


_CITY_FIX = None


def _fix_cities(text: str) -> str:
    """Show well-known cities in their usual spelling ("Jaypur" -> "Jaipur"): known spelling variants, plus a close match for longer words."""
    global _CITY_FIX
    import difflib
    import re

    import flow
    import forms

    if _CITY_FIX is None:
        _CITY_FIX = {k: v for k, v in flow.CITY_ALIASES.items() if len(k) >= 4}
    def one(m):
        w = m.group(0)
        lw = w.lower()
        if lw in _CITY_FIX:
            return _CITY_FIX[lw]
        if len(lw) >= 6:
            hit = difflib.get_close_matches(w.title(), forms.CITIES, n=1, cutoff=0.86)
            if hit and hit[0].lower() != lw:
                return hit[0]
        return w
    return re.sub(r"[A-Za-z]{4,}", one, text)


def fix_terms(text: str) -> str:
    import re

    try:
        import spelling
        text = spelling.normalize(text)
    except Exception:
        pass

    for pattern, good in _TERM_FIXES:
        text = re.sub(pattern, good, text, flags=re.I)
    return text


def transcribe_api(audio: np.ndarray, rate: int = 16000) -> str:
    """Listen through VoiceStudio's OpenAI-style /v1/audio/transcriptions: the same GPU server that speaks also listens."""
    import requests

    import voice

    buf = io.BytesIO()
    sf.write(buf, audio, rate, format="WAV", subtype="PCM_16")
    data = {"model": "whisper-1", "response_format": "json", "prompt": API_HINT}
    language = os.environ.get("STT_LANGUAGE", "hi")
    if language != "auto":                          # auto = let the model detect Hindi, English or a mix
        data["language"] = language
    r = requests.post(voice.VOICESTUDIO_URL.rstrip("/") + "/v1/audio/transcriptions",
                      files={"file": ("audio.wav", buf.getvalue(), "audio/wav")},
                      data=data, headers=voice.auth_headers(), timeout=60)
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


def transcribe_gemini(audio: np.ndarray, rate: int = 16000) -> str:
    buf = io.BytesIO()
    sf.write(buf, audio, rate, format="WAV", subtype="PCM_16")
    data = base64.b64encode(buf.getvalue()).decode()
    message = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "input_audio", "input_audio": {"data": data, "format": "wav"}},
    ]}]
    for attempt in range(2):
        try:
            reply = brain._llm.chat.completions.create(model=STT_LLM_MODEL, messages=message, max_tokens=400, temperature=0)
            break
        except RateLimitError:                      # free tier: 15 requests per minute
            if attempt:
                raise
            time.sleep(20)
    text = (reply.choices[0].message.content or "").strip()
    return "" if text.strip("[]. \n").lower() == "silence" else text
