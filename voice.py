"""VoiceStudio voice: settings and a text-to-speech call with a disk cache.

All spoken replies are written by Gemini in real time (brain.py). The cache only avoids
regenerating a sentence that has already been spoken; it never decides what is said.
"""
import hashlib
import os
import time
import re

import requests

VOICESTUDIO_URL = os.environ.get("VOICESTUDIO_URL", "http://localhost:3900")   # GPU server address later
VOICE_ID = os.environ.get("VOICE_ID", "07c6a52e")                              # "Hindi Narrator"
VOICE_LANGUAGE = os.environ.get("VOICE_LANGUAGE", "hi")                        # ISO code sent with every request
VOICE_SPEED = float(os.environ.get("VOICE_SPEED", "1.0"))                     # 1.0 = normal conversation pace (0.85 sounds like a narrator)
VOICE_NUM_STEP = int(os.environ.get("VOICE_NUM_STEP", "0"))                    # 0 = VoiceStudio's default (16); try 8 to 12 for speed
LIVE_FORMAT = os.environ.get("VOICE_FORMAT", "wav")                            # live replies: "mp3" is about 10x smaller than "wav" over a slow link
VOICESTUDIO_API_KEY = os.environ.get("VOICESTUDIO_API_KEY", "")               # set when VoiceStudio runs on a remote GPU (Kaggle, a rented server)
TTS_URL = VOICESTUDIO_URL.rstrip("/") + "/v1/audio/speech"
# Voice character (not speed). VoiceStudio adds a "broadcast" sound by default, which sounds like a radio voice-over; "raw" leaves the voice as it is.
# A little sampling variation (0.3 to 0.7) makes the pitch move more, like a person talking. Leave both empty for the old behaviour.
VOICE_EFFECT = os.environ.get("VOICE_EFFECT", "")                               # "", "raw", "warm", "podcast", "broadcast" ...
VOICE_VARIATION = os.environ.get("VOICE_VARIATION", "")                         # "" or a number such as 0.5 (the engine's class_temperature)
GENERATE_URL = VOICESTUDIO_URL.rstrip("/") + "/generate"


def auth_headers() -> dict:
    """Bearer key for a remote VoiceStudio; empty for the local one."""
    return {"Authorization": f"Bearer {VOICESTUDIO_API_KEY}"} if VOICESTUDIO_API_KEY else {}

# ---- optional online voice: ElevenLabs (off by default; Ria stays fully offline unless VOICE_ENGINE=elevenlabs) ----
ENGINE = os.environ.get("VOICE_ENGINE", "voicestudio").strip().lower()
ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVEN_VOICE_NAME = os.environ.get("ELEVENLABS_VOICE_NAME", "Monika Sogam")        # looked up by name when no id is given
ELEVEN_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")          # eleven_flash_v2_5 is faster, slightly less natural
_ELEVEN = "https://api.elevenlabs.io"


def _eleven_headers() -> dict:
    return {"xi-api-key": ELEVEN_KEY}


def _eleven_resolve_voice() -> str:
    """Voice id of the wanted ElevenLabs voice: ELEVENLABS_VOICE_ID, else search the account, else the public Voice Library (and add it to the account)."""
    vid = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if vid:
        return vid
    if not ELEVEN_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    want = ELEVEN_VOICE_NAME.lower()
    r = requests.get(_ELEVEN + "/v1/voices", headers=_eleven_headers(), timeout=30)
    r.raise_for_status()
    for v in r.json().get("voices", []):
        if want in v.get("name", "").lower():
            return v["voice_id"]
    r = requests.get(_ELEVEN + "/v1/shared-voices", params={"search": ELEVEN_VOICE_NAME, "page_size": 20}, headers=_eleven_headers(), timeout=30)
    r.raise_for_status()
    for v in r.json().get("voices", []):
        if want in v.get("name", "").lower():
            a = requests.post(f"{_ELEVEN}/v1/voices/add/{v['public_owner_id']}/{v['voice_id']}", json={"new_name": v["name"]}, headers=_eleven_headers(), timeout=30)
            a.raise_for_status()
            return a.json().get("voice_id", v["voice_id"])
    raise RuntimeError(f"ElevenLabs voice '{ELEVEN_VOICE_NAME}' not found: set ELEVENLABS_VOICE_ID (copy it from the voice's page)")


if ENGINE == "elevenlabs":
    VOICE_ID = "eleven:" + _eleven_resolve_voice()                                  # also keeps this voice's audio cache and clips apart from every other voice


def _eleven_synth(sentence: str, fmt: str, lang: str = None) -> bytes:
    pcm = fmt == "wav"                                                              # the recorded clips are .wav: ask for raw PCM and wrap it
    body = {"text": sentence, "model_id": ELEVEN_MODEL, "language_code": lang or VOICE_LANGUAGE,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "speed": max(0.7, min(1.2, VOICE_SPEED))}}
    r = requests.post(f"{_ELEVEN}/v1/text-to-speech/{VOICE_ID.split(':', 1)[1]}", params={"output_format": "pcm_24000" if pcm else "mp3_44100_128"},
                      json=body, headers=_eleven_headers(), timeout=60)
    r.raise_for_status()
    if not pcm:
        return r.content
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(r.content)
    return buf.getvalue()


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_cache")

COMPANY = "लक्ष्मी इंडिया फाइनेंस लिमिटेड"

# Emergency only: spoken if Gemini or the data source fails, so the caller is never left in silence.
LINES = {
    "system_problem": "माफ़ कीजिए, अभी मैं यह जाँच नहीं कर पा रही हूँ। हमारी टीम आपको कॉल करेगी।",
}


# ---------------------- turning written numbers into words the voice says correctly ----------------------
_UNDER_100 = "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे".split()
_UNITS = ((10_000_000, "करोड़"), (100_000, "लाख"), (1_000, "हज़ार"), (100, "सौ"))
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def hindi_words(n: int) -> str:
    """4,10,000 -> 'चार लाख दस हज़ार'; 2026 -> 'दो हज़ार छब्बीस'."""
    if n == 0:
        return _UNDER_100[0]
    parts = []
    for size, name in _UNITS:
        q, n = divmod(n, size)
        if q:
            parts.append(f"{hindi_words(q)} {name}")
    if n:
        parts.append(_UNDER_100[n])
    return " ".join(parts)


def _digit_words(digits: str) -> str:
    return ", ".join(_UNDER_100[int(d)] for d in digits)


_SAYS_AI = [(re.compile(r"(एआई|ए आई|\bA\.?I\.?(?![A-Za-z]))\s*(असिस्टेंट|सहायक|assistant)", re.I), "ऑटोमेटेड असिस्टेंट"),
            (re.compile(r"आर्टिफ़?िशियल इंटेलिजेंस|artificial intelligence", re.I), "कंप्यूटर प्रोग्राम"),
            (re.compile(r"एआई|ए आई(?![\u0900-\u097F])|\bA\.?I\.?(?![A-Za-z])"), "ऑटोमेटेड सिस्टम")]


def no_ai_word(text: str) -> str:
    """Ria does not say "AI" (owner's choice). She still never claims to be human: she calls herself an automated assistant."""
    for pattern, word in _SAYS_AI:
        text = pattern.sub(word, text)
    return text


def speakable(text: str, lang: str = "hi") -> str:
    """Text for the voice: digits become words (amounts and dates as numbers; numbers of 9+ digits, such as phone numbers, digit by digit).
    English keeps ordinary numbers as digits (the English voice reads them) and spells out long ones digit by digit."""
    text = no_ai_word(text)
    if lang == "en":
        text = text.replace("₹", "").replace("%", " percent")
        text = re.sub(r"(?<=\d),(?=\d)", "", text)
        return re.sub(r"\d{9,}", lambda m: " ".join(m.group()), text)
    text = text.translate(_DEVANAGARI_DIGITS).replace("₹", "")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)                              # 4,10,000 -> 410000
    text = re.sub(r"(\d+)\.(\d+)", lambda m: f"{hindi_words(int(m.group(1)))} दशमलव {_digit_words(m.group(2))}", text)
    text = re.sub(r"\d+", lambda m: _digit_words(m.group()) if len(m.group()) >= 9 else hindi_words(int(m.group())), text)
    return text.replace("%", " प्रतिशत")


_WRONG_SCRIPT = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")                  # Arabic / Urdu letters the voice cannot read
_URDU_FIX = {"کیا": "क्या", "ہاں": "हाँ", "نہیں": "नहीं", "جی": "जी", "شکریہ": "धन्यवाद"}


def sanitize_reply(text: str) -> str:
    """Fix the occasional stray Urdu-script word in a Hindi reply (a rare model slip) so the voice never gets it."""
    text = no_ai_word(text)
    text = re.sub(r"</?\s*[a-zA-Z][^>]{0,30}>", "", text)                        # stray tags such as </thought>
    for bad, good in _URDU_FIX.items():
        text = text.replace(bad, good)
    return re.sub(r"\s{2,}", " ", _WRONG_SCRIPT.sub("", text)).strip()


KNOWN_PIECES = set()     # the form's own questions and short acknowledgements (set by the server): each is spoken as its own, already prepared piece
APPROVED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "approved")   # recordings the owner listened to and chose


def _plain(text: str) -> str:
    return " ".join(text.split())


def approved_list():
    """[{"text": ..., "file": ...}] of the owner's approved recordings (empty if there are none)."""
    import json
    try:
        with open(os.path.join(APPROVED_DIR, "approved.json"), encoding="utf-8") as f:
            return [e for e in json.load(f) if os.path.exists(os.path.join(APPROVED_DIR, e["file"]))]
    except (OSError, ValueError):
        return []


def approved_audio(sentence: str):
    """The approved recording of exactly this sentence, as it was approved (WAV, nothing done to it), or None."""
    want = _plain(sentence)
    for e in approved_list():
        if _plain(speakable(e["text"])) == want or _plain(e["text"]) == want:
            with open(os.path.join(APPROVED_DIR, e["file"]), "rb") as f:
                return f.read()
    return None


def split_sentences(text: str):
    """The pieces a reply is spoken in. A part of the reply that the owner has an approved recording of is always its own piece (longest first),
    so that recording is played; the rest is cut as _split_new describes."""
    text = _plain(text)
    for e in sorted(approved_list(), key=lambda e: -len(e["text"])):
        a = _plain(e["text"])
        i = text.find(a)
        if i >= 0 and (i == 0 or text[i - 2:i].rstrip()[-1:] in ".!?।") and (i + len(a) == len(text) or text[i + len(a)] == " "):
            before, after = text[:i].strip(), text[i + len(a):].strip()
            return (split_sentences(before) if before else []) + [a] + (split_sentences(after) if after else [])
    parts = [p for p in re.split(r"(?<=[.!?।])\s+", text) if p]
    if len(parts) > 1:
        for i, p in enumerate(parts):
            if p in KNOWN_PIECES and (i == 0 or len(" ".join(parts[:i]).split()) >= 3):       # a 1-2 word "ठीक है।" stays joined: alone it can sound different
                before, after = " ".join(parts[:i]), " ".join(parts[i + 1:])
                return (split_sentences(before) if before else []) + [p] + (split_sentences(after) if after else [])
    return _split_new(text)


def _split_new(text: str):
    """Speech is generated and cached in pieces. Making a piece costs about 4 seconds plus a third of its length, so a piece must play for longer
    than the next one takes to make, or there is silence in the middle of an answer. A piece therefore grows until it has at least 12 words
    (about 5 seconds of speech); the rest of the reply follows as the next piece."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?।])\s+", text) if p.strip()]
    out = []
    for p in parts:
        if out and len(out[-1].split()) < 12 and len(out[-1].split()) + len(p.split()) <= 34:
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    if len(out) > 1 and len(out[-1].split()) < 4 and len(out[-2].split()) + len(out[-1].split()) <= 34:     # no tiny last piece
        out[-2] = out[-2] + " " + out.pop()
    return out


def _synth_raw(sentence: str, fmt: str = "wav", lang: str = None, seconds: float = 0.0) -> bytes:
    if ENGINE == "elevenlabs":
        return _eleven_synth(sentence, fmt, lang)
    if VOICE_EFFECT or VOICE_VARIATION:
        return _styled_synth(sentence, lang)
    body = {"model": "tts-1", "voice": VOICE_ID, "input": sentence, "language": lang or VOICE_LANGUAGE, "speed": VOICE_SPEED, "response_format": fmt}
    if VOICE_NUM_STEP:
        body["num_step"] = VOICE_NUM_STEP                      # fewer steps = faster speech, slightly rougher
    if seconds:
        body["duration"] = seconds                             # steady pace: how long this sentence should be
    last = None
    for attempt in range(3):                                   # a busy / briefly out-of-memory voice server often works on the second try
        try:
            r = requests.post(TTS_URL, json=body, headers=auth_headers(), timeout=300)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            last = e
            print(f"  voice try {attempt + 1} failed: {type(e).__name__} {getattr(getattr(e, 'response', None), 'text', '')[:160]!r}", flush=True)
            time.sleep(1.5 * (attempt + 1))
    raise last


def _styled_synth(sentence: str, lang: str = None) -> bytes:
    """The native VoiceStudio endpoint, which also takes the sound effect and the variation; it always returns WAV (browsers play it like MP3)."""
    data = {"text": sentence, "language": lang or VOICE_LANGUAGE, "profile_id": VOICE_ID, "speed": str(VOICE_SPEED)}
    if VOICE_EFFECT:
        data["effect_preset"] = VOICE_EFFECT
    if VOICE_VARIATION:
        data["class_temperature"] = VOICE_VARIATION
    if VOICE_NUM_STEP:
        data["num_step"] = str(VOICE_NUM_STEP)
    last = None
    for attempt in range(3):
        try:
            r = requests.post(GENERATE_URL, data=data, headers=auth_headers(), timeout=300)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            last = e
            print(f"  voice try {attempt + 1} failed: {type(e).__name__}", flush=True)
            time.sleep(1.5 * (attempt + 1))
    raise last


# ------------------------------------------------------------------------------------------------
# Keeping the voice a woman's voice. A cloned voice drifts deeper on very short sentences (180 Hz instead of 222 Hz) and then sounds male.
# VOICE_PITCH_TARGET (Hz, 0 = off) lifts any sentence whose pitch is clearly below the target back up (at most +4 semitones). Fails open.
VOICE_PITCH_TARGET = float(os.environ.get("VOICE_PITCH_TARGET", "0"))
_FFMPEG = None


def _ffmpeg():
    global _FFMPEG
    if _FFMPEG is None:
        import glob
        import shutil
        _FFMPEG = shutil.which("ffmpeg") or next(iter(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe"))), "")
    return _FFMPEG


def _median_pitch(x, sr: int) -> float:
    import numpy as np
    x = np.interp(np.linspace(0, len(x), int(len(x) * 16000 / sr), endpoint=False), np.arange(len(x)), x).astype("float32")
    sr, n, hop, found, peak = 16000, 640, 160, [], float(np.abs(x).max() or 1.0)
    lo, hi = int(sr / 450), int(sr / 70)
    for i in range(0, len(x) - n, hop):
        z = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt((z ** 2).mean()) < 0.015 * peak:
            continue
        c = np.correlate(z, z, "full")[n - 1:]
        k = lo + int(np.argmax(c[lo:hi]))
        if c[k] > 0.45 * c[0]:
            found.append(sr / k)
    return float(np.median(found)) if len(found) >= 8 else 0.0


def _pitch_fix(wav: bytes, fmt: str) -> bytes:
    """Lift a too-deep sentence to the target pitch and return it in the wanted format (the original bytes if anything goes wrong)."""
    import io
    import subprocess
    import soundfile as sf
    ff = _ffmpeg()
    if not ff or not VOICE_PITCH_TARGET or wav[:4] != b"RIFF":
        return wav
    try:
        x, sr = sf.read(io.BytesIO(wav), dtype="float32")
        f0 = _median_pitch(x if x.ndim == 1 else x[:, 0], sr)
        ratio = min(1.26, VOICE_PITCH_TARGET / f0) if 0 < f0 < VOICE_PITCH_TARGET * 0.94 else 1.0
        if ratio <= 1.0 and fmt != "mp3":
            return wav
        af = ["-af", f"rubberband=pitch={ratio:.4f}"] if ratio > 1.0 else []
        out = ["-codec:a", "libmp3lame", "-b:a", "96k", "-f", "mp3"] if fmt == "mp3" else ["-f", "wav"]
        r = subprocess.run([ff, "-loglevel", "error", "-i", "pipe:0", *af, *out, "pipe:1"], input=wav, capture_output=True, timeout=30)
        if ratio > 1.0:
            print(f"  pitch lifted {f0:.0f} -> {f0 * ratio:.0f} Hz", flush=True)
        return r.stdout if r.returncode == 0 and r.stdout else wav
    except Exception as e:
        print("  pitch fix skipped:", type(e).__name__, flush=True)
        return wav


# The voice engine takes one sentence at a time and rejects extra requests ("worker pool is saturated"). A reply with several sentences used to
# ask for all of them at once, so the later ones were refused, retried after seconds of silence and the voice broke up. One worker, first in first out.
from concurrent.futures import ThreadPoolExecutor
_TTS_QUEUE = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")


# Word check: every sentence is listened to again with Ria's own listener (asr_server, port 3950). If sounds are missing or garbled it is made again
# (VOICE_VERIFY = how many extra tries, 0 = off) and the best take is kept. Hindi text only; if the listener is not running the take is used as it is.
VOICE_VERIFY = int(os.environ.get("VOICE_VERIFY", "0"))
ASR_URL = os.environ.get("ASR_URL", "http://127.0.0.1:3950/transcribe")
_MAX_SOUND_ERROR = 0.28


def _sounds(text: str) -> str:
    """Consonant skeleton of a Hindi/Hinglish text, so that spelling variants compare equal."""
    from translit_hi import roman
    t = re.sub(r"[^a-z ]", "", roman(text).lower())
    for a, b in (("w", "v"), ("ph", "f"), ("z", "j"), ("kh", "k"), ("gh", "g"), ("chh", "ch"), ("sh", "s"), ("th", "t"), ("dh", "d"), ("bh", "b")):
        t = t.replace(a, b)
    t = re.sub(r"[aeiouy]", "", t)
    return re.sub(r"\s+", " ", re.sub(r"(.)\1+", r"\1", t)).strip()


def _distance(a: str, b: str) -> int:
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (x != y))
    return d[-1]


def _sound_error(text: str, wav: bytes):
    """Share of the sentence's sounds that the listener did not hear (None if it could not check)."""
    import io
    import numpy as np
    import soundfile as sf
    try:
        x, sr = sf.read(io.BytesIO(wav), dtype="float32")
        x = x if x.ndim == 1 else x[:, 0]
        x = np.interp(np.linspace(0, len(x), int(len(x) * 16000 / sr), endpoint=False), np.arange(len(x)), x).astype("float32")
        buf = io.BytesIO()
        sf.write(buf, x, 16000, format="WAV", subtype="PCM_16")
        r = requests.post(ASR_URL, files={"file": ("a.wav", buf.getvalue(), "audio/wav")}, data={"beams": 1, "prompt": ""}, timeout=20)
        r.raise_for_status()
        want, heard = _sounds(text), _sounds(r.json().get("text", ""))
        return _distance(want, heard) / max(1, len(want)) if want else 0.0
    except Exception:
        return None


def _encode(wav: bytes, fmt: str) -> bytes:
    import subprocess
    ff = _ffmpeg()
    if fmt != "mp3" or not ff:
        return wav
    r = subprocess.run([ff, "-loglevel", "error", "-i", "pipe:0", "-codec:a", "libmp3lame", "-b:a", "96k", "-f", "mp3", "pipe:1"], input=wav, capture_output=True, timeout=30)
    return r.stdout if r.returncode == 0 and r.stdout else wav


# A take is never changed after it is made: a bad one is thrown away and the sentence is made again. VOICE_MIN_PITCH (Hz, 0 = off) rejects
# takes that came out deep (they sound like another, male voice).
VOICE_MIN_PITCH = float(os.environ.get("VOICE_MIN_PITCH", "0"))
_MAX_BREAK_S = 0.7


# ------------------------------------------------------------------------------------------------
# One steady speaking pace. The engine guesses how long a sentence should be from its letters: short phrases were dragged out (3 syllables a
# second) and others rushed (up to 10). VOICE_PACE (syllables a second, 0 = off) gives the engine the length from the syllable count, and a
# take that still comes out too fast or too slow is MADE AGAIN with a corrected length. The sound itself is never stretched or changed.
VOICE_PACE = float(os.environ.get("VOICE_PACE", "0"))


def _beats(text: str) -> int:
    """About how many syllables the spoken sentence has."""
    t, n = speakable(text), 0
    for i, ch in enumerate(t):
        o = ord(ch)
        if 0x904 <= o <= 0x914:
            n += 1
        elif (0x915 <= o <= 0x939 or 0x958 <= o <= 0x95F) and not (i + 1 < len(t) and t[i + 1] == "्"):
            n += 1
    return n + sum(len(re.findall(r"[aeiouy]+", w.lower())) for w in re.findall(r"[A-Za-z]+", t))


def _planned_seconds(text: str) -> float:
    pauses = len(re.findall(r"[,;]", text)) * 0.18 + max(0, len(re.findall(r"[।?!.]", text)) - 1) * 0.32
    return round(_beats(text) / VOICE_PACE + pauses + 0.45, 2)


def _speaking_rate(text: str, x, sr: int) -> float:
    """Syllables a second while speaking (pauses of 0.18 s or more are not counted); 0 if it cannot be told."""
    import numpy as np
    fr = int(sr * 0.02)
    e = np.sqrt((x[:len(x) // fr * fr].reshape(-1, fr) ** 2).mean(1))
    on = e > 0.06 * e.max()
    where = np.where(on)[0]
    if len(where) < 3:
        return 0.0
    speech = gap = 0
    for loud in on[where[0]:where[-1] + 1]:
        if loud:
            speech += 1 + (gap if gap < 9 else 0)
            gap = 0
        else:
            gap += 1
    return _beats(text) / max(speech * 0.02, 0.2)


def _problems(text: str, wav: bytes, lang: str):
    """[(weight, reason)] of what is wrong with a take: deep voice, a long break inside it, first or last word not heard, words missing."""
    import difflib
    import io
    import numpy as np
    import soundfile as sf
    found = []
    try:
        x, sr = sf.read(io.BytesIO(wav), dtype="float32")
        x = x if x.ndim == 1 else x[:, 0]
        pitch = _median_pitch(x, sr)
        if VOICE_MIN_PITCH and 0 < pitch < VOICE_MIN_PITCH:
            found.append((3 + (VOICE_MIN_PITCH - pitch) / 20, f"deep voice {pitch:.0f} Hz"))
        n_fr = int(sr * 0.02)
        e = np.sqrt((x[:len(x) // n_fr * n_fr].reshape(-1, n_fr) ** 2).mean(1))
        active = np.where(e > 0.08 * e.max())[0]
        longest = run = 0
        for k in range(active[0], active[-1] + 1):
            run = run + 1 if e[k] <= 0.04 * e.max() else 0
            longest = max(longest, run)
        if longest * 0.02 > _MAX_BREAK_S:
            found.append((2 + longest * 0.02, f"break of {longest * 0.02:.1f} s"))
        if VOICE_PACE and lang in (None, "hi") and _beats(text) >= 4:
            rate = _speaking_rate(text, x, sr)
            allowed = 0.25 if _beats(text) < 10 else 0.12          # very short phrases naturally vary more
            off = abs(rate / VOICE_PACE - 1) if rate else 0.0
            if off > allowed:
                found.append((1 + 12 * (off - allowed), f"speed {rate:.1f} instead of {VOICE_PACE:.1f}"))
        if lang not in (None, "hi"):
            return found
        y = np.interp(np.linspace(0, len(x), int(len(x) * 16000 / sr), endpoint=False), np.arange(len(x)), x).astype("float32")
        buf = io.BytesIO()
        sf.write(buf, y, 16000, format="WAV", subtype="PCM_16")
        r = requests.post(ASR_URL, files={"file": ("a.wav", buf.getvalue(), "audio/wav")}, data={"beams": 1, "prompt": ""}, timeout=20)
        r.raise_for_status()
        words = [w for w in (_sounds(w) for w in text.split()) if w]
        heard = _sounds(r.json().get("text", ""))
        got = heard.split()
        if words:
            if not got or difflib.SequenceMatcher(None, words[0].replace(" ", ""), got[0]).ratio() < 0.5:
                found.append((5, "first word not heard"))
            if not got or difflib.SequenceMatcher(None, words[-1].replace(" ", ""), got[-1]).ratio() < 0.4:
                found.append((5, "last word not heard"))
            err = _distance(" ".join(words), heard) / max(1, len(" ".join(words)))
            if err > 0.15:
                found.append((10 * err, f"{err * 100:.0f}% of the sounds not heard"))
    except Exception as e:                                  # the check must never stop the call
        print("  voice check skipped:", type(e).__name__, flush=True)
    return found


class Busy(Exception):
    """A background (patient) take was given up because a caller is waiting for the voice engine."""


def call_waiting() -> bool:      # the server replaces this: True while a call is open
    return False


def _severe(found) -> bool:
    """Faults worth making a caller wait for another take: first or last word missing, a very deep voice, a break over 1 s, many sounds missing."""
    return any(w >= 3.0 and not (r.startswith("deep") and w < 3.65) for w, r in found)


def _synth_now(sentence: str, fmt: str, lang: str, patient: bool = False):
    """(audio, clean). Live (a caller is waiting): another take only for a severe fault, at most one. Patient (background): up to VOICE_VERIFY more."""
    if ENGINE == "elevenlabs" or not (VOICE_PITCH_TARGET or VOICE_VERIFY):
        return _synth_raw(sentence, fmt, lang), True
    best, best_score, best_found = None, 1e9, []
    paced = VOICE_PACE > 0 and lang in (None, "hi")
    seconds = _planned_seconds(sentence) if paced else 0.0
    extra_takes = max(VOICE_VERIFY, 3) if paced else VOICE_VERIFY
    for attempt in range(1 + max(0, extra_takes if patient else min(1, VOICE_VERIFY))):
        if patient and attempt and call_waiting():
            raise Busy()
        wav = _synth_raw(sentence, "wav", lang, seconds)
        if paced:                                                   # spoke too fast -> give the next take more time, too slow -> less
            import io
            import soundfile as sf
            x, sr = sf.read(io.BytesIO(wav), dtype="float32")
            rate = _speaking_rate(sentence, x if x.ndim == 1 else x[:, 0], sr)
            if rate:
                seconds = round(max(0.8, seconds * min(1.25, max(0.8, rate / VOICE_PACE))), 2)
        if VOICE_PITCH_TARGET:
            wav = _pitch_fix(wav, "wav")
        found = _problems(sentence, wav, lang) if VOICE_VERIFY else []
        score = sum(w for w, _ in found)
        if score < best_score:
            best, best_score, best_found = wav, score, found
        if not found or (not patient and not _severe(found)):
            break
        print(f"  voice check: {', '.join(r for _, r in found)} (take {attempt + 1})", flush=True)
    return _encode(best, fmt), not best_found


def synth_checked(sentence: str, fmt: str = "wav", lang: str = None, patient: bool = False):
    if ENGINE == "elevenlabs":
        return _synth_now(sentence, fmt, lang, patient)
    return _TTS_QUEUE.submit(_synth_now, sentence, fmt, lang, patient).result()


def synth(sentence: str, fmt: str = "wav", lang: str = None) -> bytes:
    return synth_checked(sentence, fmt, lang, patient=True)[0]


def cache_path(sentence: str, fmt: str = "wav", lang: str = None) -> str:
    key = hashlib.sha1(f"{VOICE_ID}|{VOICE_EFFECT}|{VOICE_VARIATION}|{lang or VOICE_LANGUAGE}|{VOICE_SPEED}|{VOICE_NUM_STEP}|{VOICE_PITCH_TARGET}|{VOICE_MIN_PITCH}|checked-2|{VOICE_PACE}|{fmt}|{sentence}".encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, key + ".bin")


def audio_for(sentence: str, fmt: str = "wav", lang: str = None, patient: bool = False) -> bytes:
    """Disk cache: a sentence is generated once, then reused if it is spoken again. An approved recording always comes first."""
    if lang in (None, "hi"):
        chosen = approved_audio(sentence)
        if chosen is not None:
            return chosen                    # WAV as approved, also when mp3 was asked for: the browser plays both
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(sentence, fmt, lang)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    data, clean = synth_checked(sentence, fmt, lang, patient)
    if clean or patient:                      # a take with a small fault is played once to a waiting caller but not kept
        with open(path, "wb") as f:
            f.write(data)
    return data
