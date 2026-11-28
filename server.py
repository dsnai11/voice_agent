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
import copy
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
BARGE_ON = _setting("BARGE", "1") == "1"                  # 0 = the customer cannot interrupt Ria
THINKING_KEEP_S = 15.0                                     # how much talk is kept while a reply is being prepared
HEARD_S, HEARD_SHARE = 2.0, 0.35                           # a reply counts as not heard only if cut in its first 2 s AND its first 35 %
BARGE_RMS = float(_setting("BARGE_RMS", "0.04"))        # interruption (collection calls): the caller must be at least this loud ...
BARGE_VOICE_BLOCKS = int(_setting("BARGE_VOICE_BLOCKS", "6"))   # ... and at least this many of those loud blocks must carry a human voice (0 = loudness only)
BARGE_SPEECH_S, BARGE_WINDOW_S = 0.45, 0.7                 # ... for 0.45 s within 0.7 s, so a cough or a short "haan" does not stop Ria
FALSE_ALARM_S = 1.2                                        # after an interruption: this long with no loud sound and nothing being heard = false alarm
FALSE_FLUSH_S = 1.5                                        # ... a faint ongoing noise is checked for words after this long without a loud sound
MAX_RESUMES = 2                                            # after two false alarms in one reply she finishes it without stopping again
EARLY_S = 1.6              # microphone audio kept while Ria speaks, so a caller who answers at once does not lose the first words
PHONE_CHUNK_SILENCE_S = float(_setting("PHONE_CHUNK_SILENCE_S", "1.3"))      # slowly spoken digits stay in one piece of audio
TURN_SILENCE_S = float(_setting("TURN_SILENCE_S", "0.8"))                  # quiet this long ends the caller's turn: the replies are spoken
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
FILLER_DELAY_S = float(_setting("FILLER_DELAY_S", "3.0"))                # play a waiting phrase if writing the reply takes longer than this ...
FILLER_PER_CALL = int(_setting("FILLER_PER_CALL", "1"))                  # ... and at most this many times in one call ("ji, ek minute" everywhere sounded wrong)
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
import voiced  # noqa: E402
import lang as lang_mod  # noqa: E402
import replybank  # noqa: E402
import collection  # noqa: E402
import sales_topup  # noqa: E402
import random  # noqa: E402
import voice  # noqa: E402

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STT_HINT = "फ़ोन नंबर नौ आठ सात छह पाँच चार तीन दो एक शून्य। लोन अकाउंट नंबर। ईएमआई। पाँच लाख रुपये। पचास हज़ार।"
# One row per call in Excel (sheet "enquiries") and one full JSON file per call in calls/
COLUMNS = ["call_id", "status", "started_at", "duration_s"] + forms.KEYS + ["details_text", "details_json", "needs_check", "confirmed_fields", "customer_ref", "ticket_id", "transcript"]
CALLS_ON = [0]                    # open call pages: the background voice cache waits while a call is on, so the caller's own sentences get the voice engine first
SESSIONS = OrderedDict()          # call_id -> CallSession (kept after the call so a late Submit still works)

@contextlib.asynccontextmanager
async def lifespan(_app):
    if STT_ENGINE == "whisper":                                  # with Gemini listening, Whisper loads only if it is needed
        threading.Thread(target=_load_stt, daemon=True).start()
    _setup_voice_hooks()
    if _setting("VOICE_PREWARM", "1") == "1":                    # 0 = do not prepare the common sentences in the background
        threading.Thread(target=_prewarm_voice, daemon=True).start()
    yield


def _setup_voice_hooks():
    voice.KNOWN_PIECES.update(_form_pieces())          # the form's questions are spoken as their own, already prepared pieces
    voice.call_waiting = lambda: CALLS_ON[0] > 0       # background preparation steps aside for a caller


def _form_pieces() -> list:
    """The form's questions as single sentences (the short acknowledgements are not pieces of their own)."""
    import flow
    texts = [t for group in (flow.QUESTIONS, flow.INCOME_Q, flow.TENURE_Q) for qs in group.values() for t in qs]
    return list(dict.fromkeys(p for t in texts for p in re.split(r"(?<=[.!?।])\s+", t.strip()) if len(p.split()) >= 4))


def _form_combos() -> list:
    """What the form actually says after an answer: a short acknowledgement and the next question, as the pieces it is spoken in."""
    import flow
    questions = [qs[0] for qs in flow.QUESTIONS.values() if qs] + [qs[1] for qs in flow.QUESTIONS.values() if len(qs) > 1]
    return list(dict.fromkeys(pc for q in questions for a in flow.ACKS for pc in voice.split_sentences(f"{a} {q}")))


def _refusal_replies():
    """The sentences used when a customer refuses, does not know, asks why, or did not understand (intents.py), so they start at once."""
    import flow
    import intents
    questions = [q for v in flow.QUESTIONS.values() for q in v] + [q for v in list(flow.INCOME_Q.values()) + list(flow.TENURE_Q.values()) for q in v]
    texts = [f"{intents.SKIP_LINE} {q}" for q in questions]                       # the most used first
    # "ओके जी। <salary / work-experience question>": worded per kind of work, so they are not among the usual combinations
    texts += [f"{a} {q}" for a in flow.ACKS for v in list(flow.INCOME_Q.values()) + list(flow.TENURE_Q.values()) for q in v]
    texts += [intents.NO_THANKS_LINE, intents.STOP_LINE, intents.BUSY_LINE, "ठीक है जी, हमारी टीम आपको जल्दी ही कॉल करेगी।", "ठीक है जी, मैंने नोट कर लिया, टीम आपको उसी समय कॉल करेगी।"]
    texts += [f"{start} {q}" for start in (intents.WHY_LINE, intents.AGAIN_LINE, intents.HELP_LINE, intents.AMOUNT_LINE) for q in questions]
    return list(dict.fromkeys(pc for t in texts for pc in voice.split_sentences(t)))


def _prewarm_voice():
    """Generate Ria's common sentences once, in the background, so they play with no wait during calls (new ones are cached as they are spoken)."""
    try:
        import flow
        if voice.ENGINE == "voicestudio":                       # start from free GPU memory: a full card makes every sentence take 30 s
            try:
                requests.post(VOICESTUDIO_URL.rstrip("/") + "/system/flush-memory", headers=voice.auth_headers(), timeout=60)
            except requests.RequestException:
                pass
        import json as _j0
        with open(replybank.BANK_PATH, encoding="utf-8") as _f0:               # the reply bank answers first: they are spoken as the pieces voice.split_sentences makes
            bank_pieces = [pc for e in _j0.load(_f0)["entries"] for pc in voice.split_sentences(e["reply"])]
        wanted = list(dict.fromkeys(voice.split_sentences(brain.SLOW_ANSWER) + [pc for t in collection.all_lines() + sales_topup.all_lines() for pc in voice.split_sentences(t)] + _form_pieces() + _form_combos() + _refusal_replies() + bank_pieces + [x for t in flow.static_sentences() + IDLE_LINES for x in voice.split_sentences(t)]))     # questions every call asks come first
        todo = [] if voice.ENGINE == "elevenlabs" else [x for x in wanted if not os.path.exists(voice.cache_path(voice.speakable(x), voice.LIVE_FORMAT))
                                                       and voice.approved_audio(x) is None]
        print(f"voice cache: {len(todo)} common sentences to prepare in the background", flush=True)
        done = 0
        while todo:
            x = todo.pop(0)
            while CALLS_ON[0] > 0:
                time.sleep(1)
            try:
                voice.audio_for(voice.speakable(x), voice.LIVE_FORMAT, patient=True)
            except voice.Busy:                       # a call came in: leave the engine to the caller, do this one later
                todo.append(x)
                continue
            except Exception as e:                   # one sentence failing must not stop the preparation of all the others
                print(f"voice cache: skipped one sentence ({type(e).__name__})", flush=True)
                continue
            done += 1
            if done % 10 == 0:
                print(f"voice cache: {done} prepared, {len(todo)} to go", flush=True)
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
                while CALLS_ON[0] > 0:
                    time.sleep(1)
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


@app.get("/crm")
def crm_page():
    return FileResponse(os.path.join(WEB_DIR, "crm.html"))


@app.get("/api/demo-crm")
def api_demo_crm():
    """The DEMO collection CRM: made-up customers and what happened on their calls."""
    return {"customers": collection.customers(), "sales_customers": sales_topup.customers(), "results": collection.results()}


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
        self.early = []                 # the last EARLY_S of microphone audio heard while not listening
        self.early_chunk = False        # the chunk being collected began in that kept audio
        self.await_playback = False     # Ria's reply has been sent and the browser is still playing it
        self.barge = []                 # for the latest blocks while it plays: (loud, carries a voice)
        self.barge_prev = np.zeros(listen.BLOCK, dtype="float32")
        self.cut = False                # the customer interrupted while the rest of the reply was still being made
        self.before_reply = None        # (state of the conversation before the reply now being prepared, what the customer had said)
        self.held_back = 0              # replies held back in a row because the customer was still talking
        self.spoke_at = 0.0             # when Ria started to speak the current reply
        self.interrupted_at = 0.0       # when the customer last interrupted
        self.reply_pieces = []          # the reply being spoken: [(sentence, sound or the task that makes it)]
        self.reply_end_turn = True
        self.reply_gen = 0              # goes up when what is being sent must stop
        self.heard_whole = set()        # sentences the customer heard to the end before interrupting: not said again in the next reply
        self.taken_back = None          # (state before the reply that was taken back, state after it, how many things the customer had said)
        self.resume = None              # set after an interruption, until real words are heard (or none are: then she carries on)
        self.resumes = 0                # false alarms in the current reply
        self.loud_at = 0.0              # the last loud sound while waiting to see whether the interruption was real
        self.reply_seconds = 0.0        # how long the reply being spoken lasts
        self.fillers = 0                # waiting phrases played in this call
        self.reply_held = False         # the last reply was held back: this turn is still going on
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

    def use_collection(self, customer_id: str) -> bool:
        """Turn this call into a DEMO call to a demo-CRM customer: EMI collection, or a top-up sales call."""
        person = collection.customer(customer_id)
        if person is not None:
            self.call = collection.CollectionCall(person)
            return True
        person = sales_topup.customer(customer_id)
        if person is None:
            return False
        self.call = sales_topup.TopUpCall(person)        # a scripted call too: .collection stays True, so it is driven and saved the same way
        return True

    def has_content(self) -> bool:
        if getattr(self.call, "collection", False):
            return any(r == "caller" for r, _ in self.transcript)
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
        if getattr(self.call, "collection", False):          # demo calls are kept apart from the company's leads and queries
            await asyncio.to_thread(collection.save_result, self.call, list(self.transcript), self.call_id, self.started)
            self.ticket = {"kind": "collection", "id": None}
            return {"enquiry": None, "ticket": self.ticket}
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
                self._new_reply(True)
                self.reply_pieces = list(zip(sentences, audio))
                self.transcript.append(("agent", text))
                await self.send(type="transcript", role="agent", text=text)
            for piece, (x, wav) in enumerate(zip(sentences, audio)):
                await self.send(type="agent_audio", text=x, data=base64.b64encode(wav).decode(), piece=piece)
            return text
        clip = clips.pick(group, avoid=self.last_clip.get(group, ""))
        if clip is None:
            return None
        text, wav = clip
        self.last_clip[group] = text
        if transcript:
            self._new_reply(True)
            self.reply_pieces = [(text, wav)]
            self.transcript.append(("agent", text))
            await self.send(type="transcript", role="agent", text=text)
        await self.send(type="agent_audio", text=text, data=base64.b64encode(wav).decode(), piece=0)
        return text

    async def _filler_after(self, delay: float):
        """If the real reply is still not ready after `delay` seconds, play a short waiting phrase (rarely: FILLER_PER_CALL)."""
        await asyncio.sleep(delay)
        if self.resume is not None or self.fillers >= FILLER_PER_CALL:      # never while checking whether an interruption was real
            return
        self.fillers += 1
        print("  waiting phrase played", flush=True)
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
        if getattr(self.call, "collection", False):          # a collection call opens by asking for the customer by name
            await self.speak(self.call.opening())
            return
        if self.call_lang() != "hi":                          # a language was chosen before the call: greet in it
            import i18n
            hindi = clips.GROUPS["greeting"][0]
            self.call.start_with(hindi)
            await self.speak(i18n.localize(hindi, self.call_lang()))
            return
        recorded = await self.play_clip("greeting")
        if recorded:
            self.call.start_with(recorded)
            self._allow_interrupt()
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
        self.cut = False
        text = self._without_heard(text)
        gen = self._new_reply(end_turn)
        self.reply_seconds = 0.0
        self.transcript.append(("agent", text))
        await self.send(type="status", state="speaking")
        t0 = time.time()
        lg = self.call_lang()
        code = lang_mod.TTS_CODE[lg] if lg != "hi" else None
        jobs = [asyncio.create_task(asyncio.to_thread(voice.audio_for, voice.speakable(sentence, lg), voice.LIVE_FORMAT, code))
                for sentence in voice.split_sentences(text)]
        self.reply_pieces = list(zip(voice.split_sentences(text), jobs))
        shown = False
        for piece, (sentence, job) in enumerate(zip(voice.split_sentences(text), jobs)):
            try:
                wav = await job
            except Exception as e:
                await self.send(type="error", message=f"Voice engine failed ({type(e).__name__}). Is VoiceStudio running?")
                for j in jobs:
                    j.cancel()
                break
            if self.cut or gen != self.reply_gen:                    # interrupted while this piece was being made
                break
            if not shown:
                if self.before_reply and self._customer_talked(self.early):
                    for j in jobs:
                        j.cancel()
                    if self.transcript and self.transcript[-1] == ("agent", text):
                        self.transcript.pop()
                    self._listen_instead()
                    return
                shown = True
                self.spoke_at = time.time()
                if end_turn:
                    self._allow_interrupt()
                await self.send(type="transcript", role="agent", text=text)
                print(f"  voice: first audio ready {time.time() - t0:.1f}s after the reply was written", flush=True)
                if self._turn_t0 and "first_audio_s" not in self.cur_metrics:
                    self.cur_metrics["first_audio_s"] = round(time.time() - self._turn_t0, 2)      # from the end of the caller's turn to the first sound
            self.reply_seconds += max(0.0, (len(wav) - 44) / 48000)          # 24 kHz, 16-bit sound
            await self.send(type="agent_audio", text=sentence, data=base64.b64encode(wav).decode(), piece=piece)
        if self.cut or gen != self.reply_gen:                        # interrupted: nothing more is sent now (kept in case it was a false alarm)
            return
        if not shown:
            await self.send(type="transcript", role="agent", text=text)
        if end_turn:
            await self.send(type="turn_end")

    # --- the customer comes first (all calls)
    def _snapshot(self):
        """The conversation as it is before a reply is written, so a reply that is never spoken can be taken back."""
        try:
            call = self.call
            if getattr(call, "collection", False):
                return {k: copy.deepcopy(getattr(call, k)) for k in ("stage", "finished", "outcome", "notes", "unclear")}
            state = {k: copy.deepcopy(getattr(call, k)) for k in ("form", "flags", "confirmed", "history", "finished", "turn_no", "_turn_open")}
            if call.flow is not None:
                state["flow"] = {k: copy.deepcopy(v) for k, v in call.flow.__dict__.items() if k != "call"}
            return state
        except Exception as e:                       # never let this stop a call: the reply is then simply spoken
            print("  could not keep the state before the reply:", type(e).__name__, flush=True)
            return None

    def _restore(self, state: dict) -> None:
        for key, value in state.items():
            if key == "flow":
                self.call.flow.__dict__.update(value)
            else:
                setattr(self.call, key, value)

    def _take_back(self, state: dict, said: list) -> None:
        """A reply is taken back: the call returns to where it was before it (what it was after is remembered, see below)."""
        after = self._snapshot() if getattr(self.call, "collection", False) else None
        self.taken_back = (state, after, len(said))
        self._restore(state)

    def _keep_confirmation(self, texts: list) -> list:
        """Scripted calls: if the reply taken back was the one that followed "yes, speaking" and the customer then said something
        else, they stay confirmed and only the new words are answered. (Judged together, "haan" + "loan number yaad nahi" read as
        "not that person" and ended the call.)"""
        taken, self.taken_back = self.taken_back, None
        if not taken or not getattr(self.call, "collection", False):
            return texts
        before, after, count = taken
        new = texts[count:]
        if not (new and after and before.get("stage") == "identity" and after.get("stage") == "emi" and not after.get("finished")):
            return texts
        if not self.call.keeps_confirmation(" ".join(new)):
            return texts
        self._restore(after)
        print("  the customer stays confirmed: only the new words are answered", flush=True)
        return new

    def _loud(self, block) -> bool:
        return listen.rms(block) > max(BARGE_RMS, 3 * self.seg.thr)

    def _customer_talked(self, blocks) -> bool:
        """True if the kept audio holds real speech (0.45 s of it within 0.7 s), not a cough or a short "haan"."""
        if not (BARGE_ON and self.seg):
            return False
        width, need = int(BARGE_WINDOW_S / listen.BLOCK_S), int(BARGE_SPEECH_S / listen.BLOCK_S)
        loud = [self._loud(b) for b in blocks]
        return any(sum(loud[i:i + width]) >= need for i in range(len(loud)))

    def _allow_interrupt(self) -> None:
        """Ria has started to speak a reply: from now on the customer may interrupt it (never the goodbye)."""
        if BARGE_ON and not self.call.finished and not self.complete:
            self.barge, self.early, self.await_playback = [], [], True

    def _listen_instead(self, audio=None) -> None:
        """The customer was still talking when the reply was ready: say nothing, hear all of it, and answer it together with what came before."""
        state, said = self.before_reply
        self.before_reply = None
        self.held_back += 1
        self.reply_held = True
        self._take_back(state, said)
        kept, self.early = (list(self.early) if audio is None else audio), []
        print("  the customer is still talking: reply held back, listening first", flush=True)
        if self.seg:
            self.seg.reset()
        self._reset_turn()
        self.turn_texts, self.turn_has_audio, self.listening = list(said), True, True
        self.spawn(self.send(type="status", state="listening"))
        first = next((i for i, b in enumerate(kept) if self._loud(b)), 0)
        for block in kept[max(0, first - 12):]:
            self.early_chunk = True
            self._listen(block)

    def browser_playback_done(self):
        """The browser's "I have finished playing". Ignored if the customer's turn is already open (they started to speak and Ria stopped, or
        the message is late): opening the turn again would throw away the words already heard."""
        if self.listening or time.time() - self.interrupted_at < 1.5:
            return
        self.playback_done()

    def playback_done(self):
        """The browser finished playing the agent's turn: open the caller's turn."""
        if self.complete:
            return
        self.await_playback = False
        self.before_reply, self.held_back = None, 0
        if self.seg:
            self.seg.reset()
        self._reset_turn()
        self.listening = True
        self.spawn(self.send(type="status", state="listening"))
        kept, self.early = self.early, []
        if self.seg:
            start = self._speech_onset(kept)
            if start is not None:                       # the caller was already speaking: hear those words too
                for block in kept[start:]:
                    self.early_chunk = True
                    self._listen(block)

    def _speech_onset(self, blocks):
        """Where the caller's words begin in the kept audio: just after the last quiet gap (0.3 s) that has speech behind it; None if nothing was said."""
        loud = [listen.rms(b) > self.seg.thr for b in blocks]
        if sum(loud) < 3:
            return None
        gap = max(1, int(0.3 / listen.BLOCK_S))
        last_loud = max(i for i, v in enumerate(loud) if v)
        quiet = 0
        for i in range(last_loud, -1, -1):
            quiet = 0 if loud[i] else quiet + 1
            if quiet >= gap:
                return i
        return 0

    def _is_echo(self, text: str) -> bool:
        """True if what was heard is only the end of Ria's own last sentence coming back through the microphone."""
        said = next((t for role, t in reversed(self.transcript) if role == "agent"), "")
        heard = [w for w in voice._sounds(text).split() if w]
        tail = voice._sounds(" ".join(said.split()[-8:])).split()
        return len(heard) >= 5 and " ".join(tail).endswith(" ".join(heard))       # long and word for word her closing words: short answers like "salary loan" are never dropped

    # --- chunked listening: each chunk is transcribed at once and gets its own reply
    async def _hear(self, part: int, audio: np.ndarray, early: bool = False) -> str:
        """Transcribe one chunk and show it at once, without waiting for the replies to earlier chunks."""
        t = time.time()
        text = await asyncio.to_thread(transcribe, audio)
        self._stt_times.append(time.time() - t)
        print(f"  chunk {part}: heard in {time.time() - t:.1f}s ({len(audio) / listen.RATE:.1f}s of speech): {text!r}", flush=True)
        if early and text and self._is_echo(text):
            print("    (only Ria's own words coming back: ignored)", flush=True)
            text = ""
        if text and len(audio) / listen.RATE < 0.4 and not _short_answer(text):
            print("    (a very short sound that is not a short answer: treated as noise)", flush=True)
            text = ""
        if text and self.resume and self._own_words(text, self.resume["text"]):
            print("    (Ria's own words from the speakers: not an interruption)", flush=True)
            text = ""
        if text and self.resume and self._only_listening(text):
            print("    (only 'haan / ji' while she was speaking: she carries on)", flush=True)
            text = ""
        if text and all(w.strip(".,?!।\ufffd") in ("जा", "जाज", "जाङ", "ज", "") for w in text.split()):      # the listener's word for noise, at any time
            print("    (words made up from noise: ignored)", flush=True)
            text = ""
        if text and self.resume and self._made_up(text):
            print("    (words made up from noise: not an interruption)", flush=True)
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
                    if self.resume is not None:
                        self._real_interruption()
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
        if self.resume is not None and not self.turn_texts:                    # she was stopped, but nothing clear was said
            filler.cancel()
            await self._resume()
            return
        texts, audio_s, replies = list(self.turn_texts), self.turn_audio_s, []
        stt_s = round(sum(self._stt_times), 2)
        self._stt_times = []
        if texts:
            self.idle_prompts = 0                                                              # everything said in this turn, merged, answered once
            texts = self._keep_confirmation(texts)
            self.call.more_coming = False
            t = time.time()
            state = self._snapshot() if self.held_back < 2 else None       # held back at most twice in a row, then she speaks
            self.early, self.reply_held = [], False
            self.before_reply = (state, texts) if state is not None else None
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
                self._allow_interrupt()
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
        if self.reply_held:                       # nothing was said: this turn is still going on
            self.reply_held = False
            return
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
                if self.resume is not None and self._loud(block):
                    self.loud_at = time.time()
                self._listen(block)
            else:                                                 # Ria is speaking or thinking: keep the latest audio
                self.early.append(block)
                keep = EARLY_S
                if BARGE_ON and self.seg and not self.await_playback and self.before_reply and any(self._loud(b) for b in self.early):
                    keep = THINKING_KEEP_S                        # the customer is talking while Ria prepares: lose none of it
                del self.early[:-int(keep / listen.BLOCK_S)]
                if self.await_playback:
                    self._watch_interruption(block)

    def _watch_interruption(self, block: np.ndarray):
        """The customer starts talking while Ria is speaking, so she stops and listens (their first words are kept)."""
        loud = self._loud(block)                              # loud is not enough: hiss, knocks and rumble must not stop her
        voice_in = loud and BARGE_VOICE_BLOCKS > 0 and voiced.is_voice(np.concatenate([self.barge_prev, block]))
        self.barge_prev = block
        self.barge.append((loud, voice_in))
        del self.barge[:-int(BARGE_WINDOW_S / listen.BLOCK_S)]
        if sum(a for a, _ in self.barge) >= int(BARGE_SPEECH_S / listen.BLOCK_S) and sum(b for _, b in self.barge) >= BARGE_VOICE_BLOCKS:
            self.barge_audio = list(self.early)
            self.await_playback, self.barge, self.cut = False, [], True
            print("  the customer interrupted: Ria stops and listens", flush=True)
            self.interrupted_at = time.time()
            self.spawn(self.send(type="interrupt"))
            # Nothing is given up yet: only real words make this an interruption. Without them she carries on (_resume).
            takeback = bool(self.before_reply and self.held_back < 2 and time.time() - self.spoke_at < min(HEARD_S, HEARD_SHARE * max(self.reply_seconds, 2.0)))
            self.reply_gen += 1
            self.resume = {"takeback": takeback, "before": self.before_reply, "held": self.held_back, "from": None,
                           "elapsed": time.time() - self.spoke_at, "text": next((t for r, t in reversed(self.transcript) if r == "agent"), "")}
            self.loud_at = time.time()
            if takeback:
                self._open_turn(self.barge_audio)
            else:
                self.playback_done()
            self.spawn(self._watch_false_alarm(self.resume))

    def _open_turn(self, audio) -> None:
        """Listen at once, including the first words already kept."""
        self.early, self.before_reply = [], None
        if self.seg:
            self.seg.reset()
        self._reset_turn()
        self.listening = True
        self.spawn(self.send(type="status", state="listening"))
        first = next((i for i, b in enumerate(audio) if self._loud(b)), 0)
        for block in audio[max(0, first - 12):]:
            self.early_chunk = True
            self._listen(block)

    def _without_heard(self, text: str) -> str:
        """Drop long statements the customer already heard to the end just before interrupting. Questions are always asked, and
        something is always said."""
        heard, self.heard_whole = self.heard_whole, set()
        if not heard:
            return text
        parts = voice.split_sentences(text)
        keep = [p for p in parts if not (p in heard and len(p.split()) >= 6 and not p.rstrip().endswith("?"))]
        return " ".join(keep) if keep and len(keep) < len(parts) else text

    def _only_listening(self, text: str) -> bool:
        """"haan", "ji", "achha" said while she is still well inside her sentence: the customer is following, not answering."""
        import flow
        return bool(flow.is_ack_only(text)) and len(text.split()) <= 3 and self.resume["elapsed"] < 0.7 * max(self.reply_seconds, 2.0)

    def _new_reply(self, end_turn: bool) -> int:
        self.reply_gen += 1
        self.reply_pieces, self.reply_end_turn = [], end_turn
        self.resume, self.resumes = None, 0
        return self.reply_gen

    def _own_words(self, heard: str, said: str) -> bool:
        """True if what was heard is four or more words in a row of the reply she was speaking: her own voice from the speakers."""
        words = voice._sounds(heard).split()
        return len(words) >= 4 and f" {' '.join(words)} " in f" {voice._sounds(said)} "

    def _made_up(self, heard: str) -> bool:
        """What the listening model writes for pure noise: the "ja jaj" it produces for knocks and rumble, or one phrase looping."""
        words = [w.strip(".,?!।�").lower() for w in heard.split()]
        words = [w for w in words if w]
        if words and all(w in ("जा", "जाज", "जाङ", "ज") for w in words):
            return True
        yes_no = {"haan", "han", "ha", "nahi", "nahin", "ji", "no", "yes"}
        return len(words) >= 6 and len(set(words)) <= len(words) // 3 and not set(words) <= yes_no

    def _real_interruption(self) -> None:
        """Real words were heard after she stopped: the interruption stands."""
        r, self.resume = self.resume, None
        self.heard_whole = {s for s, _ in self.reply_pieces[: r["from"] or 0]}
        if r["takeback"] and r["before"]:                       # she had barely started: take the reply back and answer everything together
            state, said = r["before"]
            self._take_back(state, said)
            self.held_back = r["held"] + 1
            at = next((i for i in range(len(self.transcript) - 1, -1, -1) if self.transcript[i] == ("agent", r["text"])), None)
            if at is not None:
                self.transcript.pop(at)
            self.turn_texts = list(said) + self.turn_texts
            print("  the customer is still talking: reply held back, listening first", flush=True)

    async def _watch_false_alarm(self, r: dict) -> None:
        """After an interruption: if no sound worth hearing follows, carry on. (A chunk that does end is judged in end_turn.)"""
        while self.resume is r and not self.complete:
            await asyncio.sleep(0.1)
            if self.resume is not r or self.turn_ending or self.chunk_q._unfinished_tasks:
                continue
            quiet = time.time() - self.loud_at
            if self.seg and self.seg.speaking:
                if quiet >= FALSE_FLUSH_S:                      # a faint noise keeps the chunk open: check now whether it holds words
                    audio = np.concatenate(self.seg.buf)
                    self.seg.reset()
                    self._take_chunk(audio)
            elif not self.turn_has_audio and quiet >= FALSE_ALARM_S:
                await self._resume()

    async def _resume(self) -> None:
        """False alarm: nothing clear was said. Say the rest of the reply, from the start of the sentence that was cut."""
        r, self.resume = self.resume, None
        if r is None or self.complete or not self.reply_pieces:
            return
        start = r["from"]
        if start is None:                                       # the page did not say where it stopped: estimate from the lengths
            start, total = 0, 0.0
            for _sentence, item in self.reply_pieces:
                ready = isinstance(item, bytes) or (item.done() and not item.cancelled() and item.exception() is None)
                if not ready:
                    break
                wav = item if isinstance(item, bytes) else item.result()
                total += max(0.0, (len(wav) - 44) / 48000)
                if total >= r["elapsed"]:
                    break
                start += 1
        start = max(0, min(int(start), len(self.reply_pieces) - 1))
        self.resumes += 1
        self.listening, self.cut, self.interrupted_at, self.early = False, False, 0.0, []
        if self.seg:
            self.seg.reset()
        self._reset_turn()
        self.reply_gen += 1
        gen = self.reply_gen
        self.before_reply, self.held_back = (r["before"] if r["takeback"] else None), r["held"]
        self.spoke_at = time.time() - r["elapsed"]
        print(f"  false alarm (no clear words): Ria carries on from sentence {start + 1} of {len(self.reply_pieces)}", flush=True)
        await self.send(type="status", state="speaking")
        if self.resumes < MAX_RESUMES:
            self._allow_interrupt()
        for piece in range(start, len(self.reply_pieces)):
            sentence, item = self.reply_pieces[piece]
            try:
                wav = item if isinstance(item, bytes) else await item
            except Exception as e:
                await self.send(type="error", message=f"Voice engine failed ({type(e).__name__}).")
                break
            if gen != self.reply_gen:
                return
            await self.send(type="agent_audio", text=sentence, data=base64.b64encode(wav).decode(), piece=piece)
        if gen == self.reply_gen and self.reply_end_turn:
            await self.send(type="turn_end")

    def _listen(self, block: np.ndarray):
        """One block of microphone audio while the caller's turn is open."""
        if not self.listening:
            return
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
        asked_phone = self.call.flow is not None and self.call.flow.asked == "phone"
        self.seg.end_blocks = int((PHONE_CHUNK_SILENCE_S if asked_phone else CHUNK_SILENCE_S) / listen.BLOCK_S)
        chunk = self.seg.feed(block)
        if chunk is not None:                             # a chunk of speech just ended: transcribe it right away
            self._take_chunk(chunk)
        if self.turn_has_audio and not self.seg.speaking and self.silent_s >= self._turn_silence() and not self.turn_ending:
            self.turn_ending, self.listening = True, False   # quiet long enough: the turn is over
            self.spawn(self.end_turn())

    def _take_chunk(self, chunk: np.ndarray) -> None:
        self.turn_has_audio = True
        self.turn_audio_s += len(chunk) / listen.RATE
        self.chunk_idx += 1
        self.turn_parts += 1
        early, self.early_chunk = self.early_chunk, False
        stt_task = asyncio.ensure_future(self._hear(self.turn_parts, chunk, early))
        self.chunk_q.put_nowait((self.chunk_idx, chunk, stt_task))
        self._ensure_worker()

    def close(self):
        for t in list(self.tasks):
            t.cancel()


@app.websocket("/ws/call")
async def ws_call(ws: WebSocket):
    await ws.accept()
    sess = CallSession(ws, asyncio.get_running_loop())
    CALLS_ON[0] += 1
    try:
        async with asyncio.timeout(MAX_CALL_S or None):
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    sess.on_audio(msg["bytes"])
                elif msg.get("text"):
                    data = json.loads(msg["text"])
                    kind = data.get("type")
                    if kind == "start":
                        if data.get("customer") and not sess.use_collection(str(data["customer"])):
                            await sess.send(type="error", message="This customer is not in the demo CRM.")
                            break
                        flow_ = getattr(sess.call, "flow", None)
                        if flow_ is not None and data.get("lang") in ("hi", "en", "gu", "mwr"):
                            flow_.lang, flow_.fixed_lang = data["lang"], True
                        sess.start()
                    elif kind == "stopped_at":                       # where the page was in the reply when it stopped
                        if sess.resume is not None:
                            try:
                                sess.resume["from"] = int(data.get("piece"))
                            except (TypeError, ValueError):
                                pass
                    elif kind == "playback_done":
                        sess.browser_playback_done()
                    elif kind == "end":
                        break
    except TimeoutError:
        await sess.send(type="error", message="Call time limit reached.")
    finally:
        CALLS_ON[0] = max(0, CALLS_ON[0] - 1)
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
