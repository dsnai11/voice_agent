"""One-time: generate the fixed Hindi lines in VoiceStudio so they play instantly.
Run (VoiceStudio must be running):  python prewarm.py
Safe to re-run; lines already cached are skipped. Add --play to hear each line after it is ready."""
import io
import sys
import time

import voice


def main() -> None:
    play = "--play" in sys.argv
    if play:
        import sounddevice as sd
        import soundfile as sf
    for name, text in voice.LINES.items():
        for sentence in voice.split_sentences(text):   # same split as agent.py, so the cache hits
            t = time.time()
            data = voice.audio_for(sentence)
            print(f"{name:16s} ready in {time.time() - t:5.1f}s  ({len(data)} bytes)")
            if play:
                audio, rate = sf.read(io.BytesIO(data))
                sd.play(audio, rate)
                sd.wait()


if __name__ == "__main__":
    main()
