"""VoiceStudio voice: settings and a text-to-speech call with a disk cache.

All spoken replies are written by Gemini in real time (brain.py). The cache only avoids
regenerating a sentence that has already been spoken; it never decides what is said.
"""
import hashlib
import os
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


def _eleven_synth(sentence: str, fmt: str) -> bytes:
    pcm = fmt == "wav"                                                              # the recorded clips are .wav: ask for raw PCM and wrap it
    body = {"text": sentence, "model_id": ELEVEN_MODEL, "language_code": VOICE_LANGUAGE,
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


def speakable(text: str) -> str:
    """Text for the voice: digits become Hindi words (amounts and dates as numbers; numbers of 9+ digits, such as phone numbers, digit by digit)."""
    text = text.translate(_DEVANAGARI_DIGITS).replace("₹", "")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)                              # 4,10,000 -> 410000
    text = re.sub(r"(\d+)\.(\d+)", lambda m: f"{hindi_words(int(m.group(1)))} दशमलव {_digit_words(m.group(2))}", text)
    text = re.sub(r"\d+", lambda m: _digit_words(m.group()) if len(m.group()) >= 9 else hindi_words(int(m.group())), text)
    return text.replace("%", " प्रतिशत")


_WRONG_SCRIPT = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")                  # Arabic / Urdu letters the voice cannot read
_URDU_FIX = {"کیا": "क्या", "ہاں": "हाँ", "نہیں": "नहीं", "جی": "जी", "شکریہ": "धन्यवाद"}


def sanitize_reply(text: str) -> str:
    """Fix the occasional stray Urdu-script word in a Hindi reply (a rare model slip) so the voice never gets it."""
    text = re.sub(r"</?\s*[a-zA-Z][^>]{0,30}>", "", text)                        # stray tags such as </thought>
    for bad, good in _URDU_FIX.items():
        text = text.replace(bad, good)
    return re.sub(r"\s{2,}", " ", _WRONG_SCRIPT.sub("", text)).strip()


def split_sentences(text: str):
    """Speech is generated and cached one sentence at a time (first sentence starts sooner)."""
    return [p.strip() for p in re.split(r"(?<=[.!?।])\s+", text) if p.strip()]


def synth(sentence: str, fmt: str = "wav") -> bytes:
    if ENGINE == "elevenlabs":
        return _eleven_synth(sentence, fmt)
    body = {"model": "tts-1", "voice": VOICE_ID, "input": sentence, "language": VOICE_LANGUAGE, "speed": VOICE_SPEED, "response_format": fmt}
    if VOICE_NUM_STEP:
        body["num_step"] = VOICE_NUM_STEP                      # fewer steps = faster speech, slightly rougher
    r = requests.post(TTS_URL, json=body, headers=auth_headers(), timeout=300)
    r.raise_for_status()
    return r.content


def cache_path(sentence: str, fmt: str = "wav") -> str:
    key = hashlib.sha1(f"{VOICE_ID}|{VOICE_LANGUAGE}|{VOICE_SPEED}|{VOICE_NUM_STEP}|{fmt}|{sentence}".encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, key + ".bin")


def audio_for(sentence: str, fmt: str = "wav") -> bytes:
    """Disk cache: a sentence is generated once, then reused if it is spoken again."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(sentence, fmt)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    data = synth(sentence, fmt)
    with open(path, "wb") as f:
        f.write(data)
    return data
