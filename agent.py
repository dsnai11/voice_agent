"""
Voice agent: caller speaks -> Whisper (STT) -> brain.py (Gemini + company data) -> VoiceStudio -> speaker.

Run:  python agent.py
Voice: VoiceStudio only. It is slow on CPU, so repeated lines are cached on disk.
Moving to the GPU server / paid Gemini = change the SETTINGS block (or the env vars), no code changes.
"""
import io
import os
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel

# ------------------------------ SETTINGS ------------------------------
# Each can be overridden by an environment variable of the same name.
def _setting(name: str, default: str) -> str:
    return os.environ.get(name, default)


VOICESTUDIO_URL = _setting("VOICESTUDIO_URL", "http://localhost:3900")   # GPU server address later
VOICE_ID = _setting("VOICE_ID", "07c6a52e")                              # "Hindi Narrator"; ids at /v1/audio/voices
STT_LANGUAGE = _setting("STT_LANGUAGE", "hi")                            # "hi" = Hindi; "" = auto-detect
VOICE_SPEED = _setting("VOICE_SPEED", "0.85")                            # agent speaking speed; 1.0 = normal, lower = slower
STT_MODEL_SIZE = _setting("STT_MODEL_SIZE", "small")                     # GPU: "medium"
STT_DEVICE = _setting("STT_DEVICE", "cpu")                               # GPU: "cuda"
STT_COMPUTE = _setting("STT_COMPUTE", "int8")                            # GPU: "float16"
LLM_MODEL = _setting("LLM_MODEL", "gemini-3.5-flash-lite")               # key: GEMINI_API_KEY (free -> paid)
DATA_BACKEND = _setting("DATA_BACKEND", "excel")                         # "excel" or "api" (see db.py)
LISTEN_MODE = _setting("LISTEN_MODE", "auto")                            # "auto" = hands-free, "push" = Enter key
END_SILENCE_S = float(_setting("END_SILENCE_S", "1.0"))                  # pause that ends the caller's turn
# ----------------------------------------------------------------------
os.environ["LLM_MODEL"] = LLM_MODEL        # brain.py, db.py and voice.py read these
os.environ["DATA_BACKEND"] = DATA_BACKEND
os.environ["VOICESTUDIO_URL"] = VOICESTUDIO_URL
os.environ["VOICE_ID"] = VOICE_ID
os.environ["VOICE_SPEED"] = VOICE_SPEED

import brain  # noqa: E402  (must come after the settings are exported)
import listen  # noqa: E402
import voice  # noqa: E402

stt = WhisperModel(STT_MODEL_SIZE, device=STT_DEVICE, compute_type=STT_COMPUTE)
speech_threshold = 0.0   # set by calibration in main()
# Context that nudges Whisper to write spoken numbers as Hindi number words / digits.
STT_HINT = "फ़ोन नंबर नौ नौ नौ शून्य शून्य शून्य एक एक एक एक। पिन चार तीन दो एक। पाँच छह सात आठ नौ।"


def record():
    """Returns the caller's audio, or None if nobody spoke."""
    if LISTEN_MODE == "push":
        input("\nPress Enter, then speak...")
        frames = []
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                            callback=lambda indata, *_: frames.append(indata.copy())):
            input("Listening... press Enter when done.")
        return np.concatenate(frames)[:, 0] if frames else None
    print("\n[listening - speak now]", flush=True)
    return listen.listen_for_utterance(speech_threshold, end_silence_s=END_SILENCE_S)


def transcribe(audio) -> str:
    if audio is None or audio.size < 16000 * 0.3:
        return ""
    segments, _ = stt.transcribe(audio, vad_filter=True, language=STT_LANGUAGE or None, beam_size=5,
                                 initial_prompt=STT_HINT)
    return " ".join(s.text for s in segments).strip()


def speak(text: str) -> None:
    for sentence in voice.split_sentences(text):
        data, rate = sf.read(io.BytesIO(voice.audio_for(voice.speakable(sentence))))
        sd.play(data, rate)
        sd.wait()
    time.sleep(0.4)   # let the speaker tail fade so it is not heard as the caller


def main() -> None:
    global speech_threshold
    print(f"Voice agent ready (voice=VoiceStudio {VOICESTUDIO_URL}, llm={LLM_MODEL}, data={DATA_BACKEND}, listen={LISTEN_MODE}). Ctrl+C to quit.")
    if LISTEN_MODE != "push":
        print("Measuring room noise - please stay quiet for one second...", flush=True)
        speech_threshold = listen.calibrate()
        print(f"Speech threshold set to {speech_threshold:.3f}")
    call = brain.Call()
    greeting = call.opening()
    print("Agent:", greeting)
    speak(greeting)
    while True:
        audio = record()
        if audio is None:          # nobody spoke; keep waiting quietly
            continue
        user_text = transcribe(audio)
        if not user_text:
            reply = call.not_heard()
            print("(didn't catch that)\nAgent:", reply)
            speak(reply)
            continue
        print("You:  ", user_text)
        reply = call.reply(user_text)
        print("Agent:", reply)
        speak(reply)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
