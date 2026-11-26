"""Pre-recorded phrases: generic lines that never depend on what the caller said, played instantly (no waiting).

All replies that depend on the caller's words are still written by Gemini and spoken live. Only the groups below are
recorded, once, with the same VoiceStudio voice as every other sentence, and stored in audio_library/.

Build or refresh the recordings (VoiceStudio must be running; slow on CPU):   python clips.py
Listen to them one by one:                                                    python clips.py --play
A clip is only used if it was made with the current text, voice, language and speed; otherwise the app falls back to
generating that line live, exactly as before.
"""
import json
import os
import random
import sys

import voice

LIB_DIR = os.environ.get("AUDIO_LIBRARY_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_library"))
MANIFEST = os.path.join(LIB_DIR, "manifest.json")

# group -> variants (one is picked at random so Ria does not sound like a loop)
GROUPS = {
    # played the moment the call connects; includes the AI disclosure and the first question
    "greeting": [
        "नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस लिमिटेड से। मैं आपकी जानकारी यहाँ नोट करूँगी। कृपया अपना पूरा नाम बताइए।",
        "नमस्ते, लक्ष्मी इंडिया फाइनेंस लिमिटेड में आपका स्वागत है। मैं रिया हूँ। सबसे पहले, कृपया अपना नाम बताइए।",
    ],
    # played if the real reply is not ready after about a second; neutral, so it fits any reply that follows
    "filler": [
        "जी, एक मिनट।",
        "ठीक है, एक मिनट।",
        "जी, मैं देख रही हूँ।",
        "जी, बस एक सेकंड।",
    ],
    # played when nothing clear was heard
    "not_heard": [
        "माफ़ कीजिए, आपकी आवाज़ साफ़ नहीं आई। कृपया दोहराइए।",
        "क्षमा कीजिए, मैं सुन नहीं पाई। कृपया एक बार फिर बोलिए।",
        "जी, आपकी आवाज़ मुझे ठीक से सुनाई नहीं दी। क्या आप दोबारा बोल सकते हैं?",
        "सॉरी, आवाज़ थोड़ी कट रही है। कृपया एक बार फिर से बता दीजिए।",
        "जी, मुझे आपकी बात ठीक से सुनाई नहीं दी। कृपया एक बार फिर बोलिए।",
    ],
    # played after the agent has finished (Gemini calls finish_call); makes no promises
    "closing": [
        "लक्ष्मी इंडिया फाइनेंस लिमिटेड से बात करने के लिए आपका बहुत धन्यवाद। आपका दिन शुभ हो, नमस्कार।",
        "आपके समय के लिए धन्यवाद। लक्ष्मी इंडिया फाइनेंस लिमिटेड की तरफ़ से आपका दिन शुभ हो, नमस्कार।",
        "धन्यवाद, आपसे बात करके अच्छा लगा। लक्ष्मी इंडिया फाइनेंस लिमिटेड की ओर से नमस्कार।",
    ],
    # played if Gemini or the data source fails, so the caller is never left in silence
    "system_problem": [voice.LINES["system_problem"]],
}


def _settings() -> dict:
    return {"voice": voice.VOICE_ID, "language": voice.VOICE_LANGUAGE, "speed": voice.VOICE_SPEED, "effect": voice.VOICE_EFFECT, "variation": voice.VOICE_VARIATION}


def _manifest() -> dict:
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _name(group: str, i: int) -> str:
    return f"{group}_{i + 1}"


def available(group: str):
    """[(text, wav_bytes)] for the clips of this group that exist and match the current text and voice settings."""
    chosen = [(t, voice.approved_audio(t)) for t in GROUPS.get(group, [])]
    chosen = [(t, a) for t, a in chosen if a is not None]
    if chosen:                                       # the owner approved a recording for this group: only approved ones are played
        return chosen
    manifest, out = _manifest(), []
    for i, text in enumerate(GROUPS.get(group, [])):
        entry = manifest.get(_name(group, i))
        path = os.path.join(LIB_DIR, _name(group, i) + ".wav")
        if entry and entry.get("text") == text and all((entry.get(k) or "") == (v or "") for k, v in _settings().items()) and os.path.exists(path):
            with open(path, "rb") as f:
                out.append((text, f.read()))
    return out


def pick(group: str, avoid: str = ""):
    """A random clip (text, wav_bytes) from the group, or None if none is recorded yet. Avoids repeating `avoid`."""
    clips = available(group)
    if len(clips) > 1:
        clips = [c for c in clips if c[0] != avoid] or clips
    return random.choice(clips) if clips else None


def build(play: bool = False) -> None:
    """Generate every missing or outdated clip with VoiceStudio and record it in the manifest."""
    os.makedirs(LIB_DIR, exist_ok=True)
    manifest = _manifest()
    todo = [(g, i, t) for g, texts in GROUPS.items() for i, t in enumerate(texts)]
    for n, (group, i, text) in enumerate(todo, 1):
        name, path = _name(group, i), os.path.join(LIB_DIR, _name(group, i) + ".wav")
        entry = manifest.get(name)
        if entry and entry.get("text") == text and all((entry.get(k) or "") == (v or "") for k, v in _settings().items()) and os.path.exists(path):
            print(f"[{n}/{len(todo)}] {name}: already recorded", flush=True)
        else:
            print(f"[{n}/{len(todo)}] {name}: generating ... {text[:50]}", flush=True)
            data = voice.synth(text)
            with open(path, "wb") as f:
                f.write(data)
            manifest[name] = {"text": text, **_settings()}
            with open(MANIFEST, "w", encoding="utf-8") as f:           # saved after every clip, so a crash loses nothing
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            print(f"           done ({len(data)} bytes)", flush=True)
        if play:
            import io

            import sounddevice as sd
            import soundfile as sf

            print(f"           playing {name}", flush=True)
            audio, rate = sf.read(io.BytesIO(open(path, "rb").read()))
            sd.play(audio, rate)
            sd.wait()
    print("Library ready." if all(available(g) for g in GROUPS) else "Some clips are still missing.")


if __name__ == "__main__":
    build(play="--play" in sys.argv)
