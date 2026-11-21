"""A live call through the running app in each language: speech in (made with the voice engine), what was heard, what Ria answered and in which language.
    python train/lang_call_test.py      (the app, VoiceStudio, the listener and Ollama must be running; English must pass, Gujarati / Marwari are informational
    because the test speech is synthetic)"""
import asyncio, base64, io, json, re, sys
import numpy as np, requests, soundfile as sf, websockets
sys.stdout.reconfigure(encoding="utf-8")
APP = "ws://localhost:8000/ws/call"
VOICE = "http://localhost:3900/v1/audio/speech"
DEV, GU = re.compile(r"[ऀ-ॿ]"), re.compile(r"[઀-૿]")
CALLS = {
    "en": ("en", ["My name is Rahul Mehta", "I need a personal loan of two lakh rupees", "What is the interest rate?"], lambda t: not DEV.search(t) and not GU.search(t) and re.search(r"[A-Za-z]", t), True),
    "gu": ("gu", ["મારું નામ રાહુલ મહેતા છે", "મને બે લાખ રૂપિયાની પર્સનલ લોન જોઈએ છે", "વ્યાજ દર કેટલો છે"], lambda t: bool(GU.search(t)), False),
    "mwr": ("hi", ["म्हारो नाम राहुल मेहता है", "म्हने दो लाख रुपया री लोन चाइजे", "ब्याज कितो लागसी"], lambda t: bool(DEV.search(t)), False),
}


def speech(text, code):
    r = requests.post(VOICE, json={"model": "tts-1", "voice": "507e7da2", "input": text, "language": code, "speed": 0.9, "response_format": "wav", "num_step": 12}, timeout=120)
    a, sr = sf.read(io.BytesIO(r.content), dtype="float32")
    a = a if a.ndim == 1 else a[:, 0]
    a = np.interp(np.linspace(0, len(a), int(len(a) * 16000 / sr), endpoint=False), np.arange(len(a)), a)
    a = a * (0.35 / (np.abs(a).max() or 1))
    return (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()


async def stream(ws, pcm):
    for i in range(0, len(pcm), 2560):
        await ws.send(pcm[i:i + 2560])
        await asyncio.sleep(0.08)


async def one(lg):
    code, said, ok_script, strict = CALLS[lg]
    quiet = b"\x00\x00" * 16000
    ev = asyncio.Event()
    got = {"agent": [], "user": [], "audio": 0}
    async with websockets.connect(APP, max_size=None) as ws:
        async def reader():
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "agent_audio":
                    got["audio"] += len(base64.b64decode(m["data"]))
                elif m.get("type") == "transcript":
                    (got["agent"] if m["role"] == "agent" else got["user"]).append(m["text"])
                elif m.get("type") == "turn_end":
                    ev.set()
        task = asyncio.create_task(reader())
        await ws.send(json.dumps({"type": "start"}))
        await asyncio.wait_for(ev.wait(), 90)
        passed = True
        for t in said:
            ev.clear()
            await ws.send(json.dumps({"type": "playback_done"}))
            await stream(ws, quiet)
            await stream(ws, speech(t, code))
            await stream(ws, quiet * 3)
            await asyncio.wait_for(ev.wait(), 120)
            reply = got["agent"][-1]
            ok = bool(ok_script(reply))
            passed = passed and ok
            print(f"  [{lg}] said : {t}\n        heard: {got['user'][-1] if got['user'] else '(nothing)'}\n        Ria  : {reply[:150]}   {'ok' if ok else 'WRONG LANGUAGE'}")
        await ws.send(json.dumps({"type": "end"}))
        await asyncio.sleep(1)
        task.cancel()
    return passed


bad = 0
for lg in CALLS:
    ok = asyncio.run(one(lg))
    if not ok and CALLS[lg][3]:
        bad += 1
    print(f"{lg}: {'ok' if ok else 'not fully in the caller language' + ('  <-- FAIL' if CALLS[lg][3] else ' (informational)')}")
print("LANGUAGE CALL TEST:", "OK" if not bad else "FAILED")
sys.exit(1 if bad else 0)
