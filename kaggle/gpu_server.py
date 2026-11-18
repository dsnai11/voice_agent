"""Ria on a rented GPU (written for Kaggle, works on any Linux GPU box with internet).

Everything runs on this one machine, so the stages talk over localhost with no internet hops:
  VoiceStudio  port 3900   speaks (/v1/audio/speech) and listens (/v1/audio/transcriptions)
  Ollama       port 11434  the language model (OpenAI-style, with tools)
  Ria app      port 8000   server.py and the call page; ONE public tunnel address for the browser

Kaggle notebook settings: Accelerator = GPU (T4 x2 best), Internet = On. Then, in cells:
    1. !git clone --depth 1 https://github.com/debpalash/VoiceStudio /kaggle/working/VoiceStudio
    2. !cp /kaggle/input/datasets/<you>/ria-app/gpu_server.py /kaggle/working/     (this file travels inside ria_app.zip)
    3. %run /kaggle/working/gpu_server.py install
    4. %run /kaggle/working/gpu_server.py app        (needs ria_app.zip as a Kaggle dataset: see KAGGLE.md)
After one good run:  %run /kaggle/working/gpu_server.py cache-save   (then save ria_cache.tar as a private dataset: no re-downloads next time)
Models only (no app, two tunnels for the laptop):   %run /kaggle/working/gpu_server.py start
Re-running any step is safe. Use fake or test data only on Kaggle.
"""
import glob
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

WORK = os.environ.get("WORK_DIR", "/kaggle/working")
REPO = os.path.join(WORK, "VoiceStudio")
APP = os.path.join(WORK, "ria")
LOG_DIR = os.path.join(WORK, "logs")
VOICE_PORT, LLM_PORT, APP_PORT = 3900, 11434, 8000
LLM_PULL = os.environ.get("LLM_PULL", "qwen2.5:7b")          # starting candidate: change it, then run llm_eval.py
LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")         # "ollama" = small model on this GPU; "gemini" = Google's API (needs GEMINI_API_KEY; test data only)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
ASR_MODEL = os.environ.get("ASR_MODEL", "deepdml/faster-whisper-large-v3-turbo-ct2")      # the listening model VoiceStudio uses for /v1/audio/transcriptions
LICENCE_REPOS = ["k2-fsa/OmniVoice", "eustlb/higgs-audio-v2-tokenizer"]
KEY_FILE = os.path.join(WORK, "voicestudio_api_key.txt")
VOICE_FILE = os.path.join(WORK, "ria_voice_id.txt")           # id of the imported Hindi Narrator voice
BUN = os.path.expanduser("~/.bun/bin/bun")
# Everything that is slow to download lives under /kaggle/working, so it can be packed into one cache file and reused after a restart
# /kaggle/working is capped at 20 GB; /kaggle/temp has far more room and the models only need to last for the session
SCRATCH = "/kaggle/temp" if WORK.startswith("/kaggle") else WORK       # a plain folder on the big root disk; created on first use
os.makedirs(SCRATCH, exist_ok=True)
OLLAMA_DIR = os.environ.get("OLLAMA_DIR", os.path.join(SCRATCH, "ollama_models"))
os.environ["OLLAMA_MODELS"] = OLLAMA_DIR
os.makedirs(OLLAMA_DIR, exist_ok=True)
os.environ.setdefault("HF_HOME", os.path.join(SCRATCH, "hf"))
CACHE_DIRS = ["ollama_models", "hf", "omnivoice_data", "voicestudio_api_key.txt", "ria_voice_id.txt"]
CACHE_FILE = os.path.join(WORK, "ria_cache.tar")


def cache_save():
    """Pack the downloaded models and server data into ria_cache.tar (about 9 GB). Save it as a private Kaggle dataset: see KAGGLE.md."""
    present = [d for d in CACHE_DIRS if os.path.exists(os.path.join(WORK, d))]
    run(["tar", "-cf", CACHE_FILE, "-C", WORK] + present, what="packing the cache")
    print(f"\nCache written: {CACHE_FILE} ({os.path.getsize(CACHE_FILE) / 1e9:.1f} GB), containing: {present}")


def cache_load():
    """If a cache dataset is attached and the models are not here yet, unpack it instead of downloading everything again."""
    if os.path.isdir(OLLAMA_DIR) and os.listdir(OLLAMA_DIR):
        return
    found = glob.glob("/kaggle/input/**/ria_cache.tar", recursive=True)
    if found:
        print("Unpacking the model cache from", found[0], flush=True)
        run(["tar", "-xf", found[0], "-C", WORK], what="unpacking the cache")
    else:
        print("No model cache dataset attached: everything will be downloaded (about 9 GB). Run 'cache-save' afterwards to avoid this next time.")


def run(cmd, cwd=None, what=""):
    print(f"\n$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}", flush=True)
    if subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str)).returncode != 0:
        raise SystemExit(f"FAILED: {what or cmd}. Scroll up for the error; re-running is safe.")


def up(url, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def install():
    if not shutil.which("nvidia-smi"):
        print("WARNING: no GPU. In Kaggle: Settings -> Accelerator -> GPU, then restart the session.")
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.isdir(os.path.join(REPO, ".git")):
        run(["git", "clone", "--depth", "1", "https://github.com/debpalash/VoiceStudio", REPO], what="git clone")
    run("apt-get -qq update && apt-get -qq install -y ffmpeg libsndfile1 libportaudio2 zstd", what="apt-get")
    os.environ["PATH"] = os.path.dirname(BUN) + os.pathsep + os.environ["PATH"]
    if not os.path.exists(BUN):
        run("curl -fsSL https://bun.sh/install | bash", what="bun installer")
    if not os.path.exists(os.path.join(REPO, "frontend", "dist", "index.html")):
        run([BUN, "install", "--frozen-lockfile"], cwd=REPO, what="bun install")
        run([BUN, "run", "--cwd", "electron", "build:web"], cwd=REPO, what="web build")
    if not shutil.which("uv"):
        run([sys.executable, "-m", "pip", "install", "-q", "uv"], what="pip install uv")
    os.environ.setdefault("UV_HTTP_TIMEOUT", "300")
    run(["uv", "pip", "install", "--system", "--no-cache", "--constraint", "deploy/torch-constraints.txt", "."],
        cwd=REPO, what="VoiceStudio install")
    os.makedirs(os.path.join(REPO, ".venv"), exist_ok=True)
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "setup.py")])           # cuDNN helper; not fatal if it fails
    run([sys.executable, "-m", "pip", "install", "-q", "openai", "openpyxl", "noisereduce", "websockets", "sounddevice", "python-multipart"],
        what="Ria app packages")
    if not shutil.which("ollama"):
        run("curl -fsSL https://ollama.com/install.sh | sh", what="Ollama install")
    if not shutil.which("cloudflared"):
        run("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared"
            " && chmod +x /usr/local/bin/cloudflared", what="cloudflared download")
    print("\nInstall finished. Next: %run /kaggle/working/gpu_server.py app")


def _key():
    if os.path.exists(KEY_FILE):
        return open(KEY_FILE).read().strip()
    key = secrets.token_urlsafe(24)
    with open(KEY_FILE, "w") as f:
        f.write(key)
    return key


def _licences():
    """The voice models need their licences accepted by a person. This accepts them ONLY when the notebook sets ACCEPT_LICENCES=yes (your company's decision)."""
    import requests

    base = f"http://127.0.0.1:{VOICE_PORT}"
    for repo in LICENCE_REPOS:
        try:
            a = requests.get(f"{base}/models/licenses/details/{repo}", timeout=30).json()["acceptance"]
        except Exception as e:
            print(f"licence check for {repo} failed: {e}")
            continue
        print(f"licence {repo}: {a['license']} (category {a['category']}), state {a['state']}")
        if a["required"] and not a["accepted"]:
            if os.environ.get("ACCEPT_LICENCES") == "yes":
                r = requests.post(f"{base}/models/licenses/accept", json={"repo_id": repo, "fingerprint": a["fingerprint"], "accepted": True}, timeout=30)
                print("   accepted ->", r.status_code)
            else:
                print("   NOT accepted: speech will fail (403). After your company agrees, set os.environ['ACCEPT_LICENCES']='yes' and run this step again.")


def _listening():
    """Make sure VoiceStudio has a speech-to-text model (a fresh Kaggle machine has none); wait until it answers."""
    import io
    import wave

    import requests

    base = f"http://127.0.0.1:{VOICE_PORT}"
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    started = False
    for i in range(90):
        r = requests.post(f"{base}/v1/audio/transcriptions", files={"file": ("a.wav", buf.getvalue(), "audio/wav")},
                          data={"model": "whisper-1", "language": "hi"}, timeout=300)
        if r.status_code == 200:
            print("listening model ready.", flush=True)
            return
        if r.status_code == 409 and not started:
            print(f"installing the listening model {ASR_MODEL} (a few minutes)...", flush=True)
            requests.post(f"{base}/models/install", json={"repo_id": ASR_MODEL}, timeout=60)
            started = True
        elif r.status_code not in (409, 503):
            print("listening model check:", r.status_code, r.text[:200])
            return
        time.sleep(10)
    print("WARNING: the listening model is still not ready; the app will fall back to slow CPU Whisper.")


def _start_models(key):
    """VoiceStudio + Ollama up, models downloaded and warmed. The first request of each model is slow (loading, compiling): do it now."""
    import requests

    os.makedirs(LOG_DIR, exist_ok=True)
    if not up(f"http://127.0.0.1:{VOICE_PORT}/health"):
        env = dict(os.environ, OMNIVOICE_SERVER_MODE="1", OMNIVOICE_API_KEY=key, PYTHONUNBUFFERED="1",
                   OMNIVOICE_DATA_DIR=os.path.join(WORK, "omnivoice_data"))
        subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", str(VOICE_PORT)],
                         cwd=REPO, env=env, stdout=open(os.path.join(LOG_DIR, "voicestudio.log"), "ab"), stderr=subprocess.STDOUT)
    ollama = LLM_BACKEND == "ollama"
    if ollama and not up(f"http://127.0.0.1:{LLM_PORT}/api/tags"):
        gpus = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.count("GPU ")
        llm_env = dict(os.environ, **({"CUDA_VISIBLE_DEVICES": "1"} if gpus >= 2 else {}))     # two GPUs: the language model on the second, voice and listening on the first
        subprocess.Popen(["ollama", "serve"], env=llm_env, stdout=open(os.path.join(LOG_DIR, "ollama.log"), "ab"), stderr=subprocess.STDOUT)
    for _ in range(100):
        if up(f"http://127.0.0.1:{VOICE_PORT}/health") and (not ollama or up(f"http://127.0.0.1:{LLM_PORT}/api/tags")):
            break
        time.sleep(3)
    else:
        raise SystemExit(f"A server did not start. Look at the logs in {LOG_DIR}.")
    if ollama:
        have = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
        if LLM_PULL.split(":")[0] in have and LLM_PULL.split(":")[-1] in have:
            print(f"language model {LLM_PULL} already here: no download.")
        else:
            run(["ollama", "pull", LLM_PULL], what="model download")
    else:
        print(f"language model: Gemini ({GEMINI_MODEL}) over the internet; nothing to download.")
    run(["python", "-c", "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice')"], what="voice model download")   # instant when cached
    _licences()
    t = time.time()
    r = requests.post(f"http://127.0.0.1:{VOICE_PORT}/v1/audio/speech", timeout=900,
                      json={"model": "tts-1", "voice": "alloy", "input": "नमस्ते, मैं रिया बोल रही हूँ।", "language": "hi", "response_format": "mp3"})
    print(f"voice warm-up: status {r.status_code}, {time.time() - t:.1f}s", flush=True)
    if r.status_code == 403 and "licence" in r.text.lower():
        print("\n!! VoiceStudio will not speak until the model licences are accepted by a person. See KAGGLE.md, 'Licences'. !!\n")
    elif r.status_code != 200:
        print("voice warm-up failed:", r.text[:300])
    if ollama:
        requests.post(f"http://127.0.0.1:{LLM_PORT}/api/generate", json={"model": LLM_PULL, "prompt": "नमस्ते", "stream": False, "keep_alive": "24h"}, timeout=600)
        print("language model loaded and kept in memory.", flush=True)
    _listening()
    try:
        health = requests.get(f"http://127.0.0.1:{VOICE_PORT}/health", timeout=10).json()
        print("voice server health:", health)
        if "cuda" not in str(health.get("device", "")):
            print("WARNING: the voice server is NOT using the GPU. Check Settings -> Accelerator, restart the session and run install again.")
    except Exception as e:
        print("health check failed:", e)


def _tunnel(name, port):
    log = os.path.join(LOG_DIR, f"tunnel_{name}.log")
    open(log, "w").close()
    subprocess.Popen(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                     stdout=open(log, "ab"), stderr=subprocess.STDOUT)
    for _ in range(40):
        found = [w for w in open(log, errors="replace").read().split() if w.startswith("https://") and w.endswith("trycloudflare.com")]
        if found:
            return found[0]
        time.sleep(2)
    return None


def start():
    """Models only: two tunnel addresses for the laptop app (the older setup)."""
    key = _key()
    _start_models(key)
    voice_url, llm_url = _tunnel("voice", VOICE_PORT), _tunnel("llm", LLM_PORT)
    print("\n" + "=" * 70 + "\nCopy these into the laptop's settings (PowerShell):")
    print(f'  $env:VOICESTUDIO_URL     = "{voice_url}"\n  $env:VOICESTUDIO_API_KEY = "{key}"\n  $env:LLM_BASE_URL        = "{llm_url}/v1"')
    print(f'  $env:LLM_MODEL           = "{LLM_PULL}"\n  $env:STT_ENGINE          = "api"\n  $env:VOICE_FORMAT        = "mp3"\n' + "=" * 70)


def _import_voice():
    """Load the Hindi Narrator voice into this VoiceStudio (once per session) and return its id."""
    import requests

    if os.path.exists(VOICE_FILE):
        return open(VOICE_FILE).read().strip()
    bundle = os.path.join(APP, "Hindi_Narrator.omnivoice")
    if not os.path.exists(bundle):
        print("Hindi_Narrator.omnivoice is not in the app zip: using the stock voice 'alloy'.")
        return "alloy"
    with open(bundle, "rb") as f:
        r = requests.post(f"http://127.0.0.1:{VOICE_PORT}/marketplace/import", files={"file": ("Hindi_Narrator.omnivoice", f)}, timeout=120)
    r.raise_for_status()
    voice_id = r.json()["profile_id"]
    with open(VOICE_FILE, "w") as f:
        f.write(voice_id)
    print("Hindi Narrator imported as voice", voice_id)
    return voice_id


def app():
    """The whole Ria app on this machine: one public address, and nothing between the stages crosses the internet."""
    cache_load()
    key = _key()
    if not os.path.isdir(APP) or not os.path.exists(os.path.join(APP, "server.py")):
        found = glob.glob("/kaggle/input/**/ria_app.zip", recursive=True) + glob.glob(os.path.join(WORK, "ria_app.zip"))
        loose = [os.path.dirname(p) for p in glob.glob("/kaggle/input/**/server.py", recursive=True)]   # Kaggle unpacks uploaded zips
        if found:
            os.makedirs(APP, exist_ok=True)
            zipfile.ZipFile(found[0]).extractall(APP)
            print("Ria code unpacked from", found[0])
        elif loose:
            shutil.copytree(loose[0], APP, dirs_exist_ok=True)
            print("Ria code copied from", loose[0])
        else:
            raise SystemExit("Ria's files not found under /kaggle/input. Upload ria_app.zip as a Kaggle dataset (Add Input -> Upload) and run this again.")
    _start_models(key)
    voice_id = _import_voice()
    if LLM_BACKEND == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise SystemExit("LLM_BACKEND=gemini needs GEMINI_API_KEY in the environment (set it from a Kaggle Secret in a cell; never paste the key into the notebook).")
        llm_url, llm_model = GEMINI_URL, GEMINI_MODEL
    else:
        llm_url, llm_model = f"http://127.0.0.1:{LLM_PORT}/v1", LLM_PULL
    env = dict(os.environ, VOICESTUDIO_URL=f"http://127.0.0.1:{VOICE_PORT}", LLM_BASE_URL=llm_url, LLM_MODEL=llm_model,
               STT_ENGINE="api", VOICE_ID=voice_id, VOICE_FORMAT="mp3", VOICE_NUM_STEP=os.environ.get("VOICE_NUM_STEP", "12"),
               COMPANY_XLSX=os.path.join(APP, "company_data.xlsx"), CRM_XLSX=os.path.join(APP, "crm_demo.xlsx"),
               HOST="127.0.0.1", PORT=str(APP_PORT), PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    env.pop("VOICESTUDIO_API_KEY", None)                      # loopback needs no key
    # the fixed phrases (greeting, waiting, apology) are recorded with this voice; fast on a GPU
    subprocess.run([sys.executable, "clips.py"], cwd=APP, env=env)
    if not up(f"http://127.0.0.1:{APP_PORT}/api/health"):
        subprocess.Popen([sys.executable, "server.py"], cwd=APP, env=env,
                         stdout=open(os.path.join(LOG_DIR, "ria_app.log"), "ab"), stderr=subprocess.STDOUT)
        for _ in range(40):
            if up(f"http://127.0.0.1:{APP_PORT}/api/health"):
                break
            time.sleep(2)
        else:
            raise SystemExit(f"The Ria app did not start. Last log lines:\n{''.join(open(os.path.join(LOG_DIR, 'ria_app.log'), errors='replace').readlines()[-30:])}")
    url = _tunnel("app", APP_PORT)
    print("\n" + "=" * 70)
    print("Open this address in Chrome on your laptop, wear headphones, press Call:")
    print("  ", url or "<tunnel failed: see logs>")
    print("Timings of each turn are in the log:  !tail -f /kaggle/working/logs/ria_app.log")
    print("=" * 70)
    print("Anyone with the address can reach the app: use fake test data only. Keep this notebook session open.")


if __name__ == "__main__":
    {"install": install, "start": start, "app": app, "cache-save": cache_save}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
