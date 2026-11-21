"""End-to-end test of a real call, without a browser: connects to the running app like the call page does, speaks a few sentences
(generated with Ria's own voice engine), and checks that she greets, hears, fills the form and answers with audio.

    python train/call_test.py            (the app, VoiceStudio and the listener must be running)
"""
import asyncio
import base64
import io
import json
import sys

import numpy as np
import requests
import soundfile as sf
import websockets

sys.stdout.reconfigure(encoding="utf-8")
APP = "ws://localhost:8000/ws/call"
VOICE = "http://localhost:3900/v1/audio/speech"
SAID = ["मेरा नाम अर्जुन शर्मा है", "मुझे पाँच लाख रुपये का पर्सनल लोन चाहिए"]


def speech_pcm(text: str, voice: str = "507e7da2") -> bytes:
    r = requests.post(VOICE, json={"model": "tts-1", "voice": voice, "input": text, "language": "hi", "speed": 0.85, "response_format": "wav", "num_step": 12}, timeout=300)
    a, sr = sf.read(io.BytesIO(r.content), dtype="float32")
    if a.ndim > 1:
        a = a[:, 0]
    a = np.interp(np.linspace(0, len(a), int(len(a) * 16000 / sr), endpoint=False), np.arange(len(a)), a)
    a = a * (0.35 / (np.abs(a).max() or 1))
    return (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()


async def stream(ws, pcm: bytes):
    """Send microphone audio in real time, 80 ms at a time."""
    step = 1280 * 2
    for i in range(0, len(pcm), step):
        await ws.send(pcm[i:i + step])
        await asyncio.sleep(0.08)


async def main():
    clips = [speech_pcm(t) for t in SAID]
    quiet = b"\x00\x00" * 16000
    got = {"audio": 0, "agent": [], "user": [], "form": {}}
    done_turn = asyncio.Event()

    async with websockets.connect(APP, max_size=None) as ws:
        async def reader():
            async for raw in ws:
                m = json.loads(raw)
                t = m.get("type")
                if t == "agent_audio":
                    got["audio"] += len(base64.b64decode(m["data"]))
                elif t == "transcript":
                    (got["agent"] if m["role"] == "agent" else got["user"]).append(m["text"])
                elif t == "form":
                    got["form"] = m["values"]
                elif t == "turn_end":
                    done_turn.set()
                elif t == "error":
                    print("ERROR from app:", m["message"])
        task = asyncio.create_task(reader())
        await ws.send(json.dumps({"type": "start"}))
        await asyncio.wait_for(done_turn.wait(), 60)
        print("greeting :", got["agent"][-1] if got["agent"] else "(none)", f"| audio bytes so far: {got['audio']}")
        for text, pcm in zip(SAID, clips):
            done_turn.clear()
            await ws.send(json.dumps({"type": "playback_done"}))
            await stream(ws, quiet)                    # a second of room tone: the app measures the noise level
            await stream(ws, pcm)
            await stream(ws, quiet * 3)                # silence: the caller has finished
            await asyncio.wait_for(done_turn.wait(), 90)
            print(f"you said : {text}\n  heard  : {got['user'][-1] if got['user'] else '(nothing)'}\n  Ria    : {got['agent'][-1]}")
        await ws.send(json.dumps({"type": "end"}))
        await asyncio.sleep(2)
        task.cancel()
    f = got["form"]
    print("\nform     :", {k: v for k, v in f.items() if k != "details"}, f.get("details"))
    greeting_ok = bool(got["agent"]) and "रिया" in got["agent"][0] and "एआई" not in got["agent"][0] and "लक्ष्मी इंडिया फाइनेंस" in got["agent"][0]      # the recorded clip, not an improvised line
    if not greeting_ok:
        print("PROBLEM: the greeting is not the recorded clip:", got["agent"][:1])
    ok = greeting_ok and got["audio"] > 20000 and len(got["user"]) >= 2 and f.get("full_name")
    print("\nRESULT   :", "CALL WORKS (greeting spoken, speech heard, form filled, answers spoken)" if ok else "PROBLEM: see the lines above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
