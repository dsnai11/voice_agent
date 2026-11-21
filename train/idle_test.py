"""Silence watchdog + per-turn timing, against a test copy of the app (started by this script on port 8002 with IDLE_PROMPT_S=4).
    python train/idle_test.py        (VoiceStudio, the listener and Ollama must be running)
"""
import asyncio, base64, glob, json, os, subprocess, sys, time
import websockets
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
env = dict(os.environ, PORT="8002", IDLE_PROMPT_S="4", DENOISE="none", STT_ENGINE="hinglish", VOICE_FORMAT="mp3", VOICE_ID=os.environ.get("VOICE_ID", "507e7da2"),
           LLM_BASE_URL="http://localhost:11434/v1", LLM_MODEL="qwen2.5:7b", PYTHONIOENCODING="utf-8", COMPANY_XLSX=os.path.join(ROOT, "..", "testdata", "company_data.xlsx"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "train"))
from call_test import speech_pcm, stream


async def run():
    quiet = b"\x00\x00" * 16000
    ev = {"turn_end": asyncio.Event(), "complete": asyncio.Event()}
    got = {"agent": [], "user": []}
    async with websockets.connect("ws://localhost:8002/ws/call", max_size=None) as ws:
        async def reader():
            async for raw in ws:
                m = json.loads(raw)
                t = m.get("type")
                if t == "transcript":
                    (got["agent"] if m["role"] == "agent" else got["user"]).append(m["text"])
                elif t == "turn_end":
                    ev["turn_end"].set()
                elif t == "call_complete":
                    ev["complete"].set()
        task = asyncio.create_task(reader())
        await ws.send(json.dumps({"type": "start"}))
        await asyncio.wait_for(ev["turn_end"].wait(), 90)
        # 1) one normal turn, so a timing row exists
        ev["turn_end"].clear()
        await ws.send(json.dumps({"type": "playback_done"}))
        await stream(ws, quiet)
        await stream(ws, speech_pcm("मेरा नाम अर्जुन शर्मा है"))
        await stream(ws, quiet * 3)
        await asyncio.wait_for(ev["turn_end"].wait(), 90)
        # 2) then nobody speaks: the first prompt must come, then the polite goodbye
        ev["turn_end"].clear()
        n_before = len(got["agent"])
        await ws.send(json.dumps({"type": "playback_done"}))
        t0 = time.time()
        for _ in range(12):
            await stream(ws, quiet)
            if ev["turn_end"].is_set():
                break
        first_after = time.time() - t0
        ok1 = any("लाइन पर" in a for a in got["agent"][n_before:])
        print(f"{'ok  ' if ok1 else 'FAIL'} first prompt after {first_after:.0f}s of silence: {got['agent'][-1][:60]!r}")
        ev["turn_end"].clear()
        await ws.send(json.dumps({"type": "playback_done"}))
        for _ in range(14):
            await stream(ws, quiet)
            if ev["complete"].is_set():
                break
        ok2 = ev["complete"].is_set()
        print(f"{'ok  ' if ok2 else 'FAIL'} second silence ends the call politely: {got['agent'][-1][:70]!r}")
        await ws.send(json.dumps({"type": "end"}))
        await asyncio.sleep(2)
        task.cancel()
    return ok1 and ok2


proc = subprocess.Popen([PY, "-u", "server.py"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    import requests
    for _ in range(60):
        try:
            requests.get("http://localhost:8002/api/health", timeout=2)
            break
        except Exception:
            time.sleep(1)
    ok = asyncio.run(run())
finally:
    proc.terminate()
files = sorted(glob.glob(os.path.join(ROOT, "..", "testdata", "calls", "*.json")), key=os.path.getmtime)
rows = json.load(open(files[-1], encoding="utf-8")).get("turn_metrics", []) if files else []
ok3 = bool(rows) and "first_audio_s" in rows[0]
print(f"{'ok  ' if ok3 else 'FAIL'} per-turn timing saved with the call: {rows[:1]}")
print("IDLE TEST: ALL OK" if (ok and ok3) else "IDLE TEST: FAILED")
sys.exit(0 if (ok and ok3) else 1)
