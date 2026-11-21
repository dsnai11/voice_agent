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
import re
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime

import numpy as np
import requests
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response

# ------------------------------ SETTINGS ------------------------------
# Same names and defaults as agent.py; override with environment variables.
def _setting(name: str, default: str) -> str:
    return os.environ.get(name, default)


VOICESTUDIO_URL = _setting("VOICESTUDIO_URL", "http://localhost:3900")   # GPU server address later
VOICE_ID = _setting("VOICE_ID", "07c6a52e")
VOICE_SPEED = _setting("VOICE_SPEED", "1.0")
DENOISE = _setting("DENOISE", "spectral")                                 # noise removal before listening: "rnnoise", "spectral" or "none"
STT_ENGINE = _setting("STT_ENGINE", "gemini")                           # "gemini" (audio goes to Google), "api" (VoiceStudio on the GPU server) or "whisper" (local)
STT_LANGUAGE = _setting("STT_LANGUAGE", "hi")                            # used by the local Whisper fallback
STT_MODEL_SIZE = _setting("STT_MODEL_SIZE", "small")                     # GPU: "medium"
STT_DEVICE = _setting("STT_DEVICE", "cpu")                               # GPU: "cuda"
STT_COMPUTE = _setting("STT_COMPUTE", "int8")                            # GPU: "float16"
LLM_MODEL = _setting("LLM_MODEL", "gemini-3.5-flash-lite")
DATA_BACKEND = _setting("DATA_BACKEND", "excel")
CHUNK_SILENCE_S = float(_setting("CHUNK_SILENCE_S", "0.45"))                # a pause this long ends a chunk of the caller's speech
TURN_SILENCE_S = float(_setting("TURN_SILENCE_S", "1.0"))                  # quiet this long ends the caller's turn: the replies are spoken
IDLE_PROMPT_S = float(_setting("IDLE_PROMPT_S", "12"))                      # nobody speaks for this long: Ria asks "are you on the line?" (0 = never)
CONTINUATION_EXTRA_S = float(_setting("CONTINUATION_EXTRA_S", "0.8"))      # the caller trailed off on "aur", "ki", "matlab" ...: wait this much longer before answering
IDLE_LINES = ["जी, क्या आप लाइन पर हैं? आप आराम से बोलिए, मैं सुन रही हूँ।",
              "लगता है अभी आप बात नहीं कर पा रहे हैं। कोई बात नहीं, हमारी टीम आपको बाद में कॉल कर लेगी।"]
# a sentence that ends on one of these words is not finished yet
CONTINUATION_WORDS = {"aur", "ki", "ke", "ka", "ko", "mein", "se", "toh", "to", "matlab", "jaise", "mera", "meri", "mere", "woh", "yeh", "phir", "lekin", "par", "kyunki", "isliye", "agar", "ya", "aap", "main", "bas",
                      "and", "but", "because", "so", "the", "my", "um", "umm", "hmm", "wo", "ye", "jo", "jab", "tab", "kuch", "koi", "ek", "do", "teen", "char", "paanch", "chhe", "saat", "aath", "nau"}
PHONE_SILENCE_S = float(_setting("PHONE_SILENCE_S", "3.5"))              # while a phone number is half said, wait this long before answering
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
import lang as lang_mod  # noqa: E402
import replybank  # noqa: E402
import random  # noqa: E402
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
        todo = [] if voice.ENGINE == "elevenlabs" else [x for x in flow.static_sentences() + IDLE_LINES if not os.path.exists(voice.cache_path(voice.speakable(x), voice.LIVE_FORMAT))]
        print(f"voice cache: {len(todo)} common sentences to prepare in the background", flush=True)
        for x in todo:
            voice.audio_for(voice.speakable(x), voice.LIVE_FORMAT)
        print("voice cache ready", flush=True)
        import i18n
        import re as _re
        for lg in [x for x in _setting("PREWARM_LANGS", "en,gu,mwr").split(",") if x.strip() in ("en", "gu", "mwr")]:      # the other languages: the fixed call lines, recorded in the background
            code = lang_mod.TTS_CODE[lg]
            lines = []
            import json as _json
            with open(replybank.BANK_PATH, encoding="utf-8") as _f:
                answers = {p.strip() for e in _json.load(_f)["entries"] for p in _re.split(r"(?<=[।?!])\s+", e["reply"].strip())}      # answers are recorded when first used
            for x in flow.static_sentences() + IDLE_LINES + [t for g in ("filler", "not_heard", "closing") for t in clips.GROUPS[g]]:
                for part in _re.split(r"(?<=[।?!])\s+", x.strip()):
                    tr = i18n.table(lg).get(part.strip())
                    if tr and part.strip() not in answers:
                        lines.append(tr)
            todo2 = [x for x in dict.fromkeys(lines) if not os.path.exists(voice.cache_path(voice.speakable(x, lg), voice.LIVE_FORMAT, code))]
            print(f"voice cache {lg}: {len(todo2)} call lines to prepare in the background", flush=True)
            for x in todo2:
                voice.audio_for(voice.speakable(x, lg), voice.LIVE_FORMAT, code)
            print(f"voice cache {lg} ready", flush=True)
        try:
            if voice.ENGINE != "voicestudio":
                return
            requests.post(VOICESTUDIO_URL.rstrip("/") + "/system/flush-memory", headers=voice.auth_headers(), timeout=60)
            print("voice server GPU memory flushed", flush=True)
        except requests.RequestException:
            pass
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


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#6d5efc"/><text x="16" y="22" font-size="18" text-anchor="middle" fill="#fff" font-family="Arial" font-weight="700">R</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/form")
def api_form():
    return forms.public()


@app.get("/api/health")
def api_health():
    if voice.ENGINE == "elevenlabs":
        voicestudio = bool(voice.ELEVEN_KEY)                       # the online voice needs no local voice server
    else:
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
# A sound shorter than 0.4 s is only taken as speech when it is one of these everyday short answers (clicks and coughs are not)
SHORT_OK = {"haan", "han", "ha", "haa", "haanji", "haan ji", "ji", "ji haan", "ji nahi", "nahi", "nahin", "nhi", "nahi ji", "na", "no", "yes", "yeah", "yep", "ok", "okay", "o k", "theek", "thik", "theek hai", "thik hai",
            "sahi", "sahi hai", "hello", "hi", "hey", "bye", "bas", "acha", "accha", "achha", "achcha", "bilkul", "sure", "done", "ruko", "ruk", "stop", "bolo", "boliye", "sunao", "kya", "kaun", "ji sir", "ji madam",
            "namaste", "namaskar", "thanks", "thank you", "shukriya", "dhanyavad", "kal", "aaj", "abhi", "baad mein", "zero", "one", "do", "teen", "char", "paanch", "chhe", "saat", "aath", "nau", "ek", "shunya", "double"}


def _short_answer(text: str) -> bool:
    """A sound under 0.4 s counts as speech only if it is an everyday short answer, a city, a work type or a number (not a click or a cough)."""
    t = re.sub(r"[^a-z ]", "", text.lower()).strip()
    if t in SHORT_OK:
        return True
    try:
        import flow
        return bool(flow.parse_city(text, True) or flow.parse_employment(text, None) or flow.digits_from_speech(text) or flow.parse_duration_years(text) is not None
                    or flow.parse_amount(text, minimum=100) or flow.speak_time(text))
    except Exception:
        return False


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
        self.idle_s = 0.0               # how long nobody has said anything since Ria stopped speaking
        self.idle_prompts = 0           # 'are you there?' prompts in a row
        self.turn_metrics = []          # one row per turn: heard / reply / first-audio timing, saved with the call
        self.cur_metrics = {}
        self._stt_times = []
        self._turn_t0 = 0.0
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
                "transcript_turns": [{"role": r, "text": t} for r, t in self.transcript], "turn_metrics": self.turn_metrics}
        await asyncio.to_thread(db.save_call_json, full)
        enquiry = await asyncio.to_thread(db.save_enquiry, record, COLUMNS)
        return {"enquiry": enquiry, "ticket": info}

    def call_lang(self) -> str:
        fl = getattr(self.call, "flow", None)
        return getattr(fl, "lang", "hi") or "hi"

    async def play_clip(self, group: str, transcript: bool = True):
        """Play a pre-recorded phrase instantly. Returns its text, or None if none is recorded (callers then fall back to live).
        In English / Gujarati / Marwari the same line is said in that language (from the translation tables, spoken from the voice cache)."""
        lg = self.call_lang()
        if lg != "hi" and group in clips.GROUPS and group != "greeting":
            import i18n
            texts = clips.GROUPS[group]
            pick = [t for t in texts if t != self.last_clip.get(group)] or texts
            hi_text = random.choice(pick)
            self.last_clip[group] = hi_text
            text = i18n.localize(hi_text, lg)
            code = lang_mod.TTS_CODE[lg]
            sentences = voice.split_sentences(text)
            audio = [await asyncio.to_thread(voice.audio_for, voice.speakable(x, lg), voice.LIVE_FORMAT, code) for x in sentences]
            if transcript:
                self.transcript.append(("agent", text))
                await self.send(type="transcript", role="agent", text=text)
            for x, wav in zip(sentences, audio):
                await self.send(type="agent_audio", text=x, data=base64.b64encode(wav).decode())
            return text
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
        lg = self.call_lang()
        code = lang_mod.TTS_CODE[lg] if lg != "hi" else None
        jobs = [asyncio.create_task(asyncio.to_thread(voice.audio_for, voice.speakable(sentence, lg), voice.LIVE_FORMAT, code))
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
                if self._turn_t0 and "first_audio_s" not in self.cur_metrics:
                    self.cur_metrics["first_audio_s"] = round(time.time() - self._turn_t0, 2)      # from the end of the caller's turn to the first sound
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
        self._stt_times.append(time.time() - t)
        print(f"  chunk {part}: heard in {time.time() - t:.1f}s ({len(audio) / listen.RATE:.1f}s of speech): {text!r}", flush=True)
        if text and len(audio) / listen.RATE < 0.4 and not _short_answer(text):
            print("    (a very short sound that is not a short answer: treated as noise)", flush=True)
            text = ""
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
        """Takes the chunks in the order they were spoken and collects what each one says. The reply is written once, in end_turn,
        for everything the caller said in this turn: a pause in the middle of a sentence or a phone number must not split it."""
        while True:
            _idx, _audio, stt_task = await self.chunk_q.get()
            try:
                try:
                    part = await stt_task
                except Exception:
                    part = ""
                if part:
                    self.not_heard_streak = 0
                    self.turn_texts.append(part)
                    self.transcript.append(("caller", part))
            finally:
                self.chunk_q.task_done()

    def _turn_silence(self) -> float:
        """How long the caller must be quiet before the turn ends. Longer while a phone number is half said."""
        fl = self.call.flow
        if fl is not None and fl.asked == "phone":
            import flow as _flow
            have = len(fl.phone_buf) + len(_flow.digits_from_speech(" ".join(self.turn_texts)))
            if 0 < have < 10 or not self.turn_texts:
                return PHONE_SILENCE_S
        if self.turn_texts:                                                        # the last words say whether the caller is finished
            last = re.findall(r"[a-z]+", self.turn_texts[-1].lower())
            if last and last[-1] in CONTINUATION_WORDS and not self.turn_texts[-1].rstrip().endswith((".", "?", "!")):
                return TURN_SILENCE_S + CONTINUATION_EXTRA_S
        return TURN_SILENCE_S

    async def idle_prompt(self):
        """Nobody has spoken for a while. First time: ask if they are still on the line. Second time: say goodbye politely and end the call."""
        self.idle_prompts += 1
        if self.idle_prompts == 1:
            import i18n
            await self.speak(i18n.localize(IDLE_LINES[0], self.call_lang()))      # the browser answers with playback_done and listening resumes
        else:
            import i18n
            await self.speak(i18n.localize(IDLE_LINES[1], self.call_lang()), end_turn=False)
            self.call.finished = True
            await self.finish()

    async def end_turn(self):
        """The caller has been quiet long enough: finish the pending chunks, then speak the replies in order."""
        await self.send(type="status", state="thinking")
        self._turn_t0 = time.time()
        self.cur_metrics = {}
        filler = asyncio.create_task(self._filler_after(FILLER_DELAY_S))      # covers a slow reply with a short phrase
        await self.chunk_q.join()
        texts, audio_s, replies = list(self.turn_texts), self.turn_audio_s, []
        stt_s = round(sum(self._stt_times), 2)
        self._stt_times = []
        if texts:
            self.idle_prompts = 0                                                              # everything said in this turn, merged, answered once
            self.call.more_coming = False
            t = time.time()
            try:
                replies = [await asyncio.to_thread(self.call.reply, " ".join(texts))]
            except Exception as e:
                print(f"  reply failed: {type(e).__name__}: {e}", flush=True)
                replies = [None]
            self.cur_metrics.update(heard=" | ".join(texts)[:120], audio_s=round(audio_s, 1), stt_s=stt_s, reply_s=round(time.time() - t, 2))
            print(f"  turn heard: {' | '.join(texts)!r} -> reply written in {time.time() - t:.1f}s", flush=True)
        filler.cancel()
        self._reset_turn()
        if not texts:                                                          # nothing clear was heard
            self.not_heard_streak += 1
            if audio_s < 0.25 or self.not_heard_streak > 3:                     # a short noise, or already asked twice: keep quiet and keep listening
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
            import i18n
            spoken = [i18n.localize(voice.LINES["system_problem"], self.call_lang())]
        for reply in spoken[:-1]:
            await self.speak(reply, end_turn=False)
        await self.speak(spoken[-1], end_turn=not self.call.finished)
        if self.cur_metrics.get("heard"):
            self.cur_metrics["total_s"] = round(time.time() - self._turn_t0, 2)
            self.turn_metrics.append({"turn": len(self.turn_metrics) + 1, **self.cur_metrics})
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
                    self.seg = listen.Segmenter(thr, end_silence_s=CHUNK_SILENCE_S, min_speech_s=0.12)     # even a single short word ("haan", "ji") counts
                    print(f"  mic threshold {thr:.4f} (median noise {float(np.median(self.noise)):.4f}, peak {max(self.noise):.4f})", flush=True)
            elif self.listening:
                self.peak = max(getattr(self, "peak", 0.0), listen.rms(block))
                if int(time.time()) != getattr(self, "_peak_t", 0) and int(time.time()) % 3 == 0:
                    self._peak_t = int(time.time())
                    print(f"  mic level peak {self.peak:.4f} vs threshold {self.seg.thr:.4f}", flush=True)
                    self.peak = 0.0
                self.silent_s = 0.0 if listen.rms(block) > self.seg.thr else self.silent_s + listen.BLOCK_S
                if self.seg.speaking or self.turn_has_audio or listen.rms(block) > self.seg.thr:
                    self.idle_s = 0.0
                else:
                    self.idle_s += listen.BLOCK_S
                    if IDLE_PROMPT_S and self.idle_s >= IDLE_PROMPT_S and not self.turn_ending and not self.complete:
                        self.idle_s, self.listening = 0.0, False
                        self.spawn(self.idle_prompt())
                chunk = self.seg.feed(block)
                if chunk is not None:                             # a chunk of speech just ended: transcribe it right away
                    self.turn_has_audio = True
                    self.turn_audio_s += len(chunk) / listen.RATE
                    self.chunk_idx += 1
                    self.turn_parts += 1
                    stt_task = asyncio.ensure_future(self._hear(self.turn_parts, chunk))
                    self.chunk_q.put_nowait((self.chunk_idx, chunk, stt_task))
                    self._ensure_worker()
                if self.turn_has_audio and not self.seg.speaking and self.silent_s >= self._turn_silence() and not self.turn_ending:
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
