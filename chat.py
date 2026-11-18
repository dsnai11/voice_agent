"""Typed text-test mode: talk to the agent by typing, with no mic, Whisper or voice (fast, free of VoiceStudio).

Run:    python chat.py
Commands while chatting:
  /new      start a fresh call (new greeting, caller must verify again)
  /silence  simulate "the caller was not heard"
  /quit     exit
Optional: python chat.py --speak   also speaks each reply through VoiceStudio (slow on CPU)
"""
import sys

import brain
import db


def show_state(call: "brain.Call") -> None:
    who = f"verified customer_id={call.customer_id}" if call.customer_id else "not verified"
    print(f"   [{who} | backend={db.BACKEND}]")


def main() -> None:
    speak = "--speak" in sys.argv
    if speak:
        import io

        import sounddevice as sd
        import soundfile as sf

        import voice

        def say(text: str) -> None:
            for s in voice.split_sentences(text):
                data, rate = sf.read(io.BytesIO(voice.audio_for(s)))
                sd.play(data, rate)
                sd.wait()
    else:
        def say(text: str) -> None:
            pass

    print("Text-test mode. /new  /silence  /quit\n")
    call = brain.Call()
    reply = call.opening()
    print("Agent:", reply)
    say(reply)
    while True:
        try:
            text = input("\nCaller: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return
        if not text:
            continue
        if text == "/quit":
            return
        if text == "/new":
            call = brain.Call()
            reply = call.opening()
        elif text == "/silence":
            reply = call.not_heard()
        else:
            reply = call.reply(text)
        print("Agent:", reply)
        show_state(call)
        say(reply)


if __name__ == "__main__":
    main()
