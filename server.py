"""
Web app: click "Call" in the browser -> live Hindi voice conversation that fills a loan-enquiry form.

Run:  python server.py        then open  http://localhost:8000
Needs VoiceStudio running (see handover) and GEMINI_API_KEY saved.

Browser <-> server over one WebSocket (/ws/call):
  browser -> server : binary = microphone audio (16 kHz mono 16-bit PCM)
                      JSON   = {"type":"start"} | {"type":"playback_done"} | {"type":"end"}
  server -> browser : JSON   = status / transcript / form / agent_audio (base64 wav) / turn_end / error
"""
import asyncio
import base64
import contextlib
import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime

import numpy as np
import requests
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse

# ------------------------------ SETTINGS ------------------------------
# Same names and defaults as agent.py; override with environment variables.
def _setting(name: str, default: str) -> str:
    return os.environ.get(name, default)


VOICESTUDIO_URL = _setting("VOICESTUDIO_URL", "http://localhost:3900")   # GPU server address later
VOICE_ID = _setting("VOICE_ID", "07c6a52e")
VOICE_SPEED = _setting("VOICE_SPEED", "0.85")
DENOISE = _setting("DENOISE", "spectral")                                 # noise removal before listening: "rnnoise", "spectral" or "none"
STT_ENGINE = _setting("STT_ENGINE", "gemini")                           # "gemini" (audio goes to Google), "api" (VoiceStudio on the GPU server) or "whisper" (local)
STT_LANGUAGE = _setting("STT_LANGUAGE", "hi")                            # used by the local Whisper fallback
STT_MODEL_SIZE = _setting("STT_MODEL_SIZE", "small")                     # GPU: "medium"
STT_DEVICE = _setting("STT_DEVICE", "cpu")                               # GPU: "cuda"
STT_COMPUTE = _setting("STT_COMPUTE", "int8")                            # GPU: "float16"
LLM_MODEL = _setting("LLM_MODEL", "gemini-3.5-flash-lite")
DATA_BACKEND = _setting("DATA_BACKEND", "excel")
CHUNK_SILENCE_S = float(_setting("CHUNK_SILENCE_S", "0.5"))                # a pause this long ends a chunk of the caller's speech
TURN_SILENCE_S = float(_setting("TURN_SILENCE_S", "1.0"))                  # quiet this long ends the caller's turn: the replies are spoken
HOST = _setting("HOST", "127.0.0.1")                                     # keep local; see notes before exposing
PORT = int(_setting("PORT", "8000"))
FILLER_DELAY_S = float(_setting("FILLER_DELAY_S", "1.0"))                # play a waiting phrase if the reply takes longer than this
MAX_CALL_S = int(_setting("MAX_CALL_S", "0"))                       # 0 = no limit on how long a call can last
STT_DEBUG = _setting("STT_DEBUG", "0") == "1"                              # 1 = save every chunk of caller audio + what was heard (for tuning the listener)
STT_DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls", "stt_debug")
_STT_DEBUG_LAST = [None]
# ----------------------------------------------------------------------
for _k, _v in dict(LLM_MODEL=LLM_MODEL, DATA_BACKEND=DATA_BACKEND, VOICESTUDIO_URL=VOICESTUDIO_URL,
                   VOICE_ID=VOICE_ID, VOICE_SPEED=VOICE_SPEED, DENOISE=DENOISE).items():
    os.environ[_k] = _v

import brain  # noqa: E402  (after the settings are exported)
import db  # noqa: E402
import forms  # noqa: E402
import clips  # noqa: E402
import denoise  # noqa: E402
import listen  # noqa: E402
import stt  # noqa: E402
import tickets  # noqa: E402
import voice  # noqa: E402

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STT_HINT = "फ़ोन नंबर नौ आठ सात छह पाँच चार तीन दो एक शून्य। लोन अकाउंट नंबर। ईएमआई। पाँच लाख रुपये। पचास हज़ार।"
# One row per call in Excel (sheet "enquiries") and one full JSON file per call in calls/
COLUMNS = ["call_id", "status", "started_at", "duration_s"] + forms.KEYS + ["details_text", "details_json", "needs_check", "confirmed_fields", "customer_ref", "ticket_id", "transcript"]
SESSIONS = OrderedDict()          # call_id -> CallSession (kept after the call so a late Submit still works)

@contextlib.asynccontextmanager
async def lifespan(_app):
    if STT_ENGINE == "whisper":                                  # with Gemini listening, Whisper loads only if it is needed
        threading.Thread(target=_load_stt, daemon=True).start()
    threading.Thread(target=_prewarm_voice, daemon=True).start()
    yield


def _prewarm_voice():
    """Generate Ria's common sentences once, in the background, so they play with no wait during calls (new ones are cached as they are spoken)."""
    try:
        import flow
        todo = [x for x in flow.static_sentences() if not os.path.exists(voice.cache_path(voice.speakable(x), voice.LIVE_FORMAT))]
        print(f"voice cache: {len(todo)} common sentences to prepare in the background", flush=True)
        for x in todo:
            voice.audio_for(voice.speakable(x), voice.LIVE_FORMAT)
        print("voice cache ready", flush=True)
    except Exception as e:
        print(f"voice cache stopped: {type(e).__name__}: {e}", flush=True)


app = FastAPI(lifespan=lifespan)
_stt = None
_stt_lock = threading.Lock()      # one Whisper run at a time
_stt_ready = threading.Event()


_stt_loading = threading.Lock()


def _load_stt():
    global _stt
    with _stt_loading:
        if _stt is not None:
            return
        from faster_whisper import WhisperModel

        _stt = WhisperModel(STT_MODEL_SIZE, device=STT_DEVICE, compute_type=STT_COMPUTE)
        _stt_ready.set()
        print(f"Whisper '{STT_MODEL_SIZE}' ready.", flush=True)


def transcribe(audio: np.ndarray) -> str:
    if audio.size < listen.RATE * 0.3:
        return ""
    raw = audio
    audio = denoise.clean(audio)                                 # background noise out before anything listens
    if STT_DEBUG:                                                # keep the audio so the listener settings can be compared offline
        try:
            import soundfile as _sf
            os.makedirs(STT_DEBUG_DIR, exist_ok=True)
            _stamp = f"{int(time.time() * 1000)}"
            _sf.write(os.path.join(STT_DEBUG_DIR, _stamp + ".wav"), raw, listen.RATE, subtype="PCM_16")
            _STT_DEBUG_LAST[0] = _stamp
        except Exception:
            pass
    if STT_ENGINE == "gemini":
        try:
            return stt.transcribe_gemini(audio)
        except Exception as e:                                   # network / quota problem: fall back to local Whisper
            print(f"Gemini listening failed ({type(e).__name__}); using Whisper instead.", flush=True)
    if STT_ENGINE == "hinglish":
        try:
            return stt.transcribe_hinglish(audio)
        except Exception as e:                                   # listening service down: do not guess, ask the caller to repeat
            print(f"Hinglish listening failed ({type(e).__name__}): {e}", flush=True)
            return ""
    if STT_ENGINE == "api":
        try:
            return stt.transcribe_api(audio)
        except Exception as e:                                   # GPU server down: fall back to local Whisper
            print(f"Remote listening failed ({type(e).__name__}); using Whisper instead.", flush=True)
    _load_stt()
    with _stt_lock:
        segments, _ = _stt.transcribe(audio, vad_filter=True, language=STT_LANGUAGE or None, beam_size=5,
                                      initial_prompt=STT_HINT)
        return " ".join(s.text for s in segments).strip()


# ------------------------------ HTTP endpoints ------------------------------
@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/api/form")
def api_form():
    return forms.public()


@app.get("/api/health")
def api_health():
    try:
        voicestudio = requests.get(VOICESTUDIO_URL.rstrip("/") + "/v1/audio/voices", headers=voice.auth_headers(), timeout=3).ok
    except requests.RequestException:
        voicestudio = False
    return {"voicestudio": voicestudio, "whisper": STT_ENGINE in ("gemini", "api", "hinglish") or _stt_ready.is_set(),
            "stt_engine": STT_ENGINE, "llm_model": LLM_MODEL,
            "data_backend": DATA_BACKEND}


@app.post("/api/submit")
async def api_submit(payload: dict):
    sess = SESSIONS.get(payload.get("call_id"))
    if sess is None:
        return JSONResponse({"ok": False, "errors": {"call": "This call is no longer known to the server. Please start a new call."}}, status_code=400)
    values = payload.get("values") or {}
    form, errors = {}, {}
    for key in forms.KEYS:
        raw = values.get(key)
        if raw in (None, ""):
            if key in forms.REQUIRED:
                errors[key] = "required"
            continue
        ok, result = forms.clean(key, raw)
        (form if ok else errors)[key] = result
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=422)
    details = {}
    for label, value in (values.get("details") or {}).items():
        ok, result = forms.clean_detail(label, value)
        if ok:
            details[result[0]] = result[1]
    form["details"] = details
    sess.call.form = form                       # the version the caller reviewed and corrected
    for key in payload.get("verified") or []:   # the user ticked "looks right" or typed the value themselves
        key = forms.norm_key(key)
        sess.call.flags.pop(key, None)
        sess.call.confirmed.add(key)
    for label, value in details.items():        # format check again on what was submitted
        key = "detail:" + label
        flag = forms.detail_flag(label, value)
        if flag and key not in sess.call.confirmed:
            sess.call.flags[key] = flag
        elif not flag:
            sess.call.flags.pop(key, None)
    for key in list(sess.call.flags):           # drop flags for details that were removed
        if key.startswith("detail:") and key[7:] not in details:
            del sess.call.flags[key]
    result = await sess.persist("submitted")
    sess.submitted = True
    return {"ok": True, "saved": result["enquiry"], "ticket": result["ticket"]}


# ------------------------------ one call = one session ------------------------------
class CallSession:
    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop):
        self.ws, self.loop = ws, loop
        self.call = brain.Call("enquiry", on_form=self._on_form, on_cards=self._on_cards)
        self.pcm = np.zeros(0, dtype="float32")
        self.noise = []                 # room-noise levels measured during the first second
        self.seg = None                 # listen.Segmenter, created once noise is measured
        self.listening = False          # True only while the caller's turn is open
        self.tasks = set()
        self.call_id = uuid.uuid4().hex[:12]
        self.started = time.time()
        self.transcript = []            # [(role, text)] role is "agent" or "caller"
        self.submitted = False
        self.ticket = None
        self.complete = False           # the agent has finished: stop listening
        self.not_heard_streak = 0       # 'please repeat' prompts in a row
        # chunked listening: speech is cut at short pauses, each chunk is transcribed and answered on its own
        self.chunk_q = asyncio.Queue()  # (index, audio, transcription task) in the order spoken
        self.worker = None
        self.chunk_idx = 0
        self.silent_s = 0.0             # how long the caller has been quiet
        self.turn_has_audio = False
        self.turn_ending = False
        self.turn_audio_s = 0.0
        self.turn_parts = 0
        self.turn_texts = []            # what was heard, one entry per chunk
        self.turn_replies = []          # the reply written for each chunk (spoken once the caller has finished)
        self.last_clip = {}             # group -> last clip text played, to avoid repeating it back to back
        SESSIONS[self.call_id] = self
        while len(SESSIONS) > 100:
            SESSIONS.popitem(last=False)

    # --- sending to the browser
    async def send(self, **msg):
        try:
            await self.ws.send_json(msg)
        except Exception:
            pass

    def _on_form(self, values, changed, flags=None, confirmed=None):          # called from the Gemini worker thread
        asyncio.run_coroutine_threadsafe(
            self.send(type="form", values=values, changed=changed, missing=forms.missing(values),
                      flags=forms.needs_check(values, flags or {}, set(confirmed or [])), confirmed=list(confirmed or [])),
            self.loop)

    def _on_cards(self, cards):                    # called from the Gemini worker thread, as soon as the CRM data is ready
        asyncio.run_coroutine_threadsafe(self.send(type="cards", cards=cards), self.loop)

    def spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # --- call flow
    def start(self):
        self.spawn(self.send(type="call", id=self.call_id))
        self.spawn(self.greet())

    def has_content(self) -> bool:
        form = self.call.form
        return any(form.get(k) for k in forms.KEYS) or bool(form.get("details")) or any(r == "caller" for r, _ in self.transcript)

    def build_record(self, status: str) -> dict:
        form = self.call.form
        details = form.get("details") or {}
        return {
            "call_id": self.call_id, "status": status,
            "started_at": datetime.fromtimestamp(self.started).strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": int(time.time() - self.started),
            **{k: form.get(k, "") for k in forms.KEYS},
            "details_text": "; ".join(f"{k}: {v}" for k, v in details.items()),
            "details_json": json.dumps(details, ensure_ascii=False),
            "needs_check": "; ".join(f"{k}: {v}" for k, v in forms.needs_check(form, self.call.flags, self.call.confirmed).items()),
            "confirmed_fields": ", ".join(sorted(self.call.confirmed)),
            "transcript": chr(10).join(f"{'Agent' if r == 'agent' else 'Caller'}: {t}" for r, t in self.transcript)[:30000],
        }

    async def persist(self, status: str) -> dict:
        """Save everything about this call: the lead or query, one Excel row, and a full JSON file.
        Rows are updated, not duplicated, by call_id."""
        record = self.build_record(status)
        details = self.call.form.get("details") or {}
        caller = {}
        if record.get("phone"):                      # the mobile number is the customer's unique ID: one registry row per number
            try:
                caller = await asyncio.to_thread(db.save_caller, record["phone"], record.get("full_name", ""), self.call_id,
                                                 record["started_at"], details.get("crm_customer_id", ""), bool(details.get("identity_verified")))
            except Exception as e:
                print("could not update the callers registry", self.call_id, e, flush=True)
        record["customer_ref"] = caller.get("customer_ref", "")
        ticket = tickets.build(record, details, submitted=(status == "submitted"))
        info = {"kind": ticket["kind"], "id": None}
        try:
            saved = await asyncio.to_thread(db.save_ticket, ticket["sheet"], ticket["row"], ticket["columns"],
                                            ticket["id_col"], ticket["prefix"])
            info["id"] = saved.get("id")
            await asyncio.to_thread(db.delete_ticket, tickets.other_sheet(ticket["kind"]), self.call_id)
        except Exception as e:                       # never lose the call record because the lead/query could not be written
            print("could not save", ticket["kind"], self.call_id, e, flush=True)
            info["error"] = type(e).__name__
        self.ticket = info
        record["ticket_id"] = info["id"] or ""
        full = {**record, "details": details, "ticket": info, "crm_access": self.call.audit,
                "transcript_turns": [{"role": r, "text": t} for r, t in self.transcript]}
        await asyncio.to_thread(db.save_call_json, full)
        enquiry = await asyncio.to_thread(db.save_enquiry, record, COLUMNS)
        return {"enquiry": enquiry, "ticket": info}

    async def play_clip(self, group: str, transcript: bool = True):
        """Play a pre-recorded phrase instantly. Returns its text, or None if none is recorded (callers then fall back to live)."""
        clip = clips.pick(group, avoid=self.last_clip.get(group, ""))
        if clip is None:
            return None
        text, wav = clip
        self.last_clip[group] = text
        if transcript:
            self.transcript.append(("agent", text))
            await self.send(type="transcript", role="agent", text=text)
        await self.send(type="agent_audio", text=text, data=base64.b64encode(wav).decode())
        return text

    async def _filler_after(self, delay: float):
        """If the real reply is still not ready after `delay` seconds, play a short waiting phrase."""
        await asyncio.sleep(delay)
        await self.play_clip("filler", transcript=False)

    async def finish(self):
        """The agent has said everything: play the recorded goodbye and stop listening."""
        await self.play_clip("closing")
        self.complete = True
        self.listening = False
        await self.send(type="call_complete")
        await self.send(type="turn_end")

    async def greet(self):
        recorded = None
        await self.send(type="status", state="speaking")
        recorded = await self.play_clip("greeting")
        if recorded:
            self.call.start_with(recorded)
            await self.send(type="turn_end")
            return
        await self.send(type="status", state="thinking")
        try:
            text = await asyncio.to_thread(self.call.opening)
        except Exception:
            text = voice.LINES["system_problem"]
        await self.speak(text)

    async def speak(self, text: str, end_turn: bool = True):
        """Send the reply one sentence at a time. Every sentence starts generating at once (sentences heard before come straight
        from the cache), and the text appears on screen together with the first audio, so what is written is what is being said."""
        self.transcript.append(("agent", text))
        await self.send(type="status", state="speaking")
        t0 = time.time()
        jobs = [asyncio.create_task(asyncio.to_thread(voice.audio_for, voice.speakable(sentence), voice.LIVE_FORMAT))
                for sentence in voice.split_sentences(text)]
        shown = False
        for sentence, job in zip(voice.split_sentences(text), jobs):
            try:
                wav = await job
            except Exception as e:
                await self.send(type="error", message=f"Voice engine failed ({type(e).__name__}). Is VoiceStudio running?")
                for j in jobs:
                    j.cancel()
                break
            if not shown:
                shown = True
                await self.send(type="transcript", role="agent", text=text)
                print(f"  voice: first audio ready {time.time() - t0:.1f}s after the reply was written", flush=True)
            await self.send(type="agent_audio", text=sentence, data=base64.b64encode(wav).decode())
        if not shown:
            await self.send(type="transcript", role="agent", text=text)
        if end_turn:
            await self.send(type="turn_end")

    def playback_done(self):
        """The browser finished playing the agent's turn: open the caller's turn."""
        if self.complete:
            return
        if self.seg:
            self.seg.reset()
        self._reset_turn()
        self.listening = True
        self.spawn(self.send(type="status", state="listening"))

    # --- chunked listening: each chunk is transcribed at once and gets its own reply
    async def _hear(self, part: int, audio: np.ndarray) -> str:
        """Transcribe one chunk and show it at once, without waiting for the replies to earlier chunks."""
        t = time.time()
        text = await asyncio.to_thread(transcribe, audio)
        print(f"  chunk {part}: heard in {time.time() - t:.1f}s ({len(audio) / listen.RATE:.1f}s of speech): {text!r}", flush=True)
        if STT_DEBUG and _STT_DEBUG_LAST[0]:
            try:
                with open(os.path.join(STT_DEBUG_DIR, _STT_DEBUG_LAST[0] + ".txt"), "w", encoding="utf-8") as _f:
                    _f.write(text)
            except OSError:
                pass
        if text:
            await self.send(type="transcript", role="user", text=text, part=part)
        return text

    def _reset_turn(self):
        self.turn_has_audio, self.turn_ending, self.turn_audio_s, self.silent_s = False, False, 0.0, 0.0
        self.turn_parts = 0
        self.turn_texts, self.turn_replies = [], []

    def _ensure_worker(self):
        if self.worker is None:
            self.worker = asyncio.create_task(self._chunk_worker())
            self.tasks.add(self.worker)

    async def _chunk_worker(self):
        """Takes the chunks in the order they were spoken, waits for each transcript, and writes that chunk's own reply."""
        while True:
            batch, heard = [await self.chunk_q.get()], []
            try:
                # Chunks that are already waiting (or arrive while earlier ones are transcribed) get one shared reply.
                pending = list(batch)
                while pending:
                    for _idx, _audio, stt_task in pending:
                        try:
                            part = await stt_task
                        except Exception:
                            part = ""
                        if part:
                            heard.append(part)
                    pending = []
                    while not self.chunk_q.empty():
                        pending.append(self.chunk_q.get_nowait())
                    batch.extend(pending)
                if not heard:
                    continue
                text = " ".join(heard)
                self.not_heard_streak = 0
                self.turn_texts.extend(heard)
                self.transcript.extend(("caller", h) for h in heard)
                # Is the caller still going? Wait until we know: the turn has closed, or more speech is already there.
                while not (self.turn_ending or not self.chunk_q.empty() or (self.seg is not None and self.seg.speaking)):
                    await asyncio.sleep(0.05)
                self.call.more_coming = (not self.chunk_q.empty()) or bool(self.seg is not None and self.seg.speaking)
                t = time.time()
                try:
                    reply = await asyncio.to_thread(self.call.reply, text)
                except Exception:
                    reply = None
                print(f"  chunk reply written in {time.time() - t:.1f}s (more speech coming: {self.call.more_coming})", flush=True)
                self.turn_replies.append(reply)
            finally:
                for _ in batch:
                    self.chunk_q.task_done()

    async def end_turn(self):
        """The caller has been quiet long enough: finish the pending chunks, then speak the replies in order."""
        await self.send(type="status", state="thinking")
        filler = asyncio.create_task(self._filler_after(FILLER_DELAY_S))      # covers a slow reply with a short phrase
        await self.chunk_q.join()
        filler.cancel()
        texts, replies, audio_s = self.turn_texts, self.turn_replies, self.turn_audio_s
        self._reset_turn()
        if not texts:                                                          # nothing clear was heard
            self.not_heard_streak += 1
            if audio_s < 0.6 or self.not_heard_streak > 3:                     # a short noise, or already asked twice: keep quiet and keep listening
                self.playback_done()
                return
            if await self.play_clip("not_heard"):
                await self.send(type="turn_end")
                return
            try:
                replies = [await asyncio.to_thread(self.call.not_heard)]
            except Exception:
                replies = []
        spoken = [r for r in replies if r]
        if not spoken:                                                         # every reply failed
            if await self.play_clip("system_problem"):
                await self.send(type="turn_end")
                return
            spoken = [voice.LINES["system_problem"]]
        for reply in spoken[:-1]:
            await self.speak(reply, end_turn=False)
        await self.speak(spoken[-1], end_turn=not self.call.finished)
        if self.call.finished:
            await self.finish()
        elif self.has_content():                                               # save after every turn: nothing is lost if the call drops
            try:
                await self.persist("submitted" if self.submitted else "partial")
            except Exception as e:
                print("autosave failed", self.call_id, e, flush=True)

    # --- microphone audio from the browser
    def on_audio(self, data: bytes):
        samples = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").astype("float32") / 32768.0
        self.pcm = np.concatenate([self.pcm, samples])
        while len(self.pcm) >= listen.BLOCK:
            block, self.pcm = self.pcm[: listen.BLOCK], self.pcm[listen.BLOCK:]
            if self.seg is None:                                  # first second: measure the room noise
                self.noise.append(listen.rms(block))
                if len(self.noise) * listen.BLOCK_S >= 1.0:
                    # The greeting may already be playing during this second: use the quietest part, not the median,
                    # and cap the result so Ria's own voice can never push the threshold above normal speech.
                    thr = min(0.04, max(0.012, float(np.percentile(self.noise, 20)) * 4.0))
                    self.seg = listen.Segmenter(thr, end_silence_s=CHUNK_SILENCE_S)
                    print(f"  mic threshold {thr:.4f} (median noise {float(np.median(self.noise)):.4f}, peak {max(self.noise):.4f})", flush=True)
            elif self.listening:
                self.peak = max(getattr(self, "peak", 0.0), listen.rms(block))
                if int(time.time()) != getattr(self, "_peak_t", 0) and int(time.time()) % 3 == 0:
                    self._peak_t = int(time.time())
                    print(f"  mic level peak {self.peak:.4f} vs threshold {self.seg.thr:.4f}", flush=True)
                    self.peak = 0.0
                self.silent_s = 0.0 if listen.rms(block) > self.seg.thr else self.silent_s + listen.BLOCK_S
                chunk = self.seg.feed(block)
                if chunk is not None:                             # a chunk of speech just ended: transcribe it right away
                    self.turn_has_audio = True
                    self.turn_audio_s += len(chunk) / listen.RATE
                    self.chunk_idx += 1
                    self.turn_parts += 1
                    stt_task = asyncio.ensure_future(self._hear(self.turn_parts, chunk))
                    self.chunk_q.put_nowait((self.chunk_idx, chunk, stt_task))
                    self._ensure_worker()
                if self.turn_has_audio and not self.seg.speaking and self.silent_s >= TURN_SILENCE_S and not self.turn_ending:
                    self.turn_ending, self.listening = True, False   # quiet long enough: the turn is over
                    self.spawn(self.end_turn())

    def close(self):
        for t in list(self.tasks):
            t.cancel()


@app.websocket("/ws/call")
async def ws_call(ws: WebSocket):
    await ws.accept()
    sess = CallSession(ws, asyncio.get_running_loop())
    try:
        async with asyncio.timeout(MAX_CALL_S or None):
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    sess.on_audio(msg["bytes"])
                elif msg.get("text"):
                    kind = json.loads(msg["text"]).get("type")
                    if kind == "start":
                        sess.start()
                    elif kind == "playback_done":
                        sess.playback_done()
                    elif kind == "end":
                        break
    except TimeoutError:
        await sess.send(type="error", message="Call time limit reached.")
    finally:
        if not sess.submitted and sess.has_content():      # call ended early: keep everything said so far
            try:
                result = await sess.persist("partial")
                await sess.send(type="saved", status="partial", ticket=result["ticket"])
            except Exception as e:
                print("could not save call", sess.call_id, e, flush=True)
        elif sess.submitted:
            await sess.send(type="saved", status="submitted", ticket=sess.ticket)
        sess.close()


if __name__ == "__main__":
    print(f"Open http://{'localhost' if HOST == '127.0.0.1' else HOST}:{PORT}   (VoiceStudio: {VOICESTUDIO_URL})")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
