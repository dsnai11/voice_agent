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
VOICE_SPEED = float(os.environ.get("VOICE_SPEED", "0.85"))                     # 1.0 = normal, lower = slower
VOICE_NUM_STEP = int(os.environ.get("VOICE_NUM_STEP", "0"))                    # 0 = VoiceStudio's default (16); try 8 to 12 for speed
LIVE_FORMAT = os.environ.get("VOICE_FORMAT", "wav")                            # live replies: "mp3" is about 10x smaller than "wav" over a slow link
VOICESTUDIO_API_KEY = os.environ.get("VOICESTUDIO_API_KEY", "")               # set when VoiceStudio runs on a remote GPU (Kaggle, a rented server)
TTS_URL = VOICESTUDIO_URL.rstrip("/") + "/v1/audio/speech"


def auth_headers() -> dict:
    """Bearer key for a remote VoiceStudio; empty for the local one."""
    return {"Authorization": f"Bearer {VOICESTUDIO_API_KEY}"} if VOICESTUDIO_API_KEY else {}
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
    body = {"model": "tts-1", "voice": VOICE_ID, "input": sentence, "language": VOICE_LANGUAGE, "speed": VOICE_SPEED, "response_format": fmt}
    if VOICE_NUM_STEP:
        body["num_step"] = VOICE_NUM_STEP                      # fewer steps = faster speech, slightly rougher
    r = requests.post(TTS_URL, json=body, headers=auth_headers(), timeout=300)
    r.raise_for_status()
    return r.content


def audio_for(sentence: str, fmt: str = "wav") -> bytes:
    """Disk cache: a sentence is generated once, then reused if it is spoken again."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(f"{VOICE_ID}|{VOICE_LANGUAGE}|{VOICE_SPEED}|{VOICE_NUM_STEP}|{fmt}|{sentence}".encode()).hexdigest()[:16]
    path = os.path.join(CACHE_DIR, key + ".bin")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    data = synth(sentence, fmt)
    with open(path, "wb") as f:
        f.write(data)
    return data
