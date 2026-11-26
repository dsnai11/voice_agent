"""Make a new Ria voice from a real recording (with the speaker's consent), test it, and print its voice id.

    python make_voice.py --audio voice.wav --consent consent.wav --speaker "Full Name" --name "Ria Human" [--text "exact words said"]

What it does: reads the recording (WAV / M4A / MP3 that soundfile can read), makes it mono 24 kHz, trims silence, checks its length and loudness,
cleans background noise with VoiceStudio, creates a clone profile, stores the consent recording with it, then says five Ria sentences in the new
voice (voice_samples/<name>/) and prints how lively the voice is compared with the current one. Nothing in the running app changes.
See voice_kit/RECORDING_SCRIPT.md for how to record.
"""
import argparse
import io
import json
import os
import sys

import numpy as np
import requests
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
VS = os.environ.get("VOICESTUDIO_URL", "http://localhost:3900").rstrip("/")
SCRIPT_TEXT = ("जी नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस से। अच्छा जी, समझ गई। आपको कितने का लोन चाहिए, लगभग? कोई बात नहीं, "
               "आप आराम से बताइए। हाँ जी, ये तो बिल्कुल हो जाएगा। बस आपकी थोड़ी सी जानकारी चाहिए, फिर हमारी टीम आपको कॉल कर लेगी। ठीक है?")
TEST_LINES = ["नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस लिमिटेड से। कृपया अपना पूरा नाम बताइए।", "अच्छा जी, समझ गई। आपको कितने का लोन चाहिए, लगभग?",
              "जी, दो लाख रुपये, नोट कर लिया। लोन किस ज़रूरत के लिए ले रहे हैं आप?", "माफ़ कीजिए, मुझे ठीक से समझ नहीं आया। क्या आप फिर से बोल सकते हैं?",
              "ठीक है जी, आपकी जानकारी नोट हो गई है और हमारी टीम जल्दी आपसे संपर्क करेगी।"]


def load(path: str, rate: int = 24000):
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    if sr != rate:
        a = np.interp(np.linspace(0, len(a), int(len(a) * rate / sr), endpoint=False), np.arange(len(a)), a).astype("float32")
    level = np.sqrt(np.convolve(a ** 2, np.ones(480) / 480, "same"))
    loud = np.where(level > max(0.01, level.max() * 0.05))[0]
    if len(loud):
        a = a[max(0, loud[0] - 2400): loud[-1] + 4800]                     # keep 0.1 s before and 0.2 s after the speech
    peak = float(np.abs(a).max() or 1)
    return (a * (0.9 / peak)).astype("float32"), rate


def wav_bytes(a, rate):
    b = io.BytesIO()
    sf.write(b, a, rate, format="WAV", subtype="PCM_16")
    return b.getvalue()


def pitch_movement(a, sr):
    n, hop, out = int(sr * 0.03), int(sr * 0.01), []
    for i in range(0, len(a) - n, hop):
        x = a[i:i + n] - np.mean(a[i:i + n])
        if np.sqrt(np.mean(x ** 2)) < 0.02:
            continue
        c = np.correlate(x, x, "full")[n - 1:]
        lo, hi = int(sr / 450), int(sr / 120)
        k = lo + int(np.argmax(c[lo:hi]))
        if c[k] > 0.4 * c[0]:
            out.append(sr / k)
    f0 = np.array(out)
    if len(f0) < 10:
        return None, None
    semis = 12 * np.log2(f0 / np.median(f0))
    return int(np.median(f0)), round(float(np.std(np.diff(semis))), 2)


def say(profile, text, effect="raw", variation="0.5"):
    r = requests.post(VS + "/generate", data={"text": text, "language": "hi", "profile_id": profile, "effect_preset": effect, "class_temperature": variation}, timeout=300)
    r.raise_for_status()
    return r.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="the voice recording (about 20 to 30 seconds)")
    ap.add_argument("--consent", help="the consent sentence recorded by the same person (strongly recommended)")
    ap.add_argument("--speaker", default="", help="the speaker's full name, stored with the consent")
    ap.add_argument("--name", default="Ria Human", help="name of the new voice in VoiceStudio")
    ap.add_argument("--text", default=SCRIPT_TEXT, help="exactly what is said in the recording")
    ap.add_argument("--no-clean", action="store_true", help="skip VoiceStudio's noise cleaning")
    args = ap.parse_args()

    a, sr = load(args.audio)
    secs = len(a) / sr
    print(f"recording: {secs:.1f} s after trimming")
    if secs < 6:
        sys.exit("too short: record at least 10 seconds of natural speech")
    if secs > 40:
        print("note: long recording, only about the first 30 seconds matter; keep it shorter for the best result")
    audio = wav_bytes(a, sr)
    if not args.no_clean:
        r = requests.post(VS + "/clean-audio", files={"audio": ("voice.wav", audio, "audio/wav")}, timeout=300)
        if r.ok and r.content[:4] == b"RIFF":
            audio = r.content
            print("background noise cleaned")
        else:
            print("noise cleaning skipped:", r.status_code, r.text[:120])
    r = requests.post(VS + "/profiles", data={"name": args.name, "ref_text": args.text, "language": "hi", "kind": "clone",
                                              "instruct": "", "personality": "friendly, warm phone voice"},
                      files={"ref_audio": ("voice.wav", audio, "audio/wav")}, timeout=300)
    r.raise_for_status()
    prof = r.json()
    pid = prof.get("id") or prof.get("profile_id")
    print(f"voice created in VoiceStudio: {args.name} (id {pid})")
    if args.consent:
        c, csr = load(args.consent)
        text = f"मैं, {args.speaker or '(नाम)'}, अपनी मर्ज़ी से अपनी आवाज़ लक्ष्मी इंडिया फाइनेंस की कॉलिंग असिस्टेंट रिया के लिए इस्तेमाल करने की अनुमति देती हूँ।"
        r = requests.post(f"{VS}/profiles/{pid}/consent", data={"consent_text": text}, files={"consent_audio": ("consent.wav", wav_bytes(c, csr), "audio/wav")}, timeout=120)
        print("consent stored with the voice" if r.ok else f"consent not stored: {r.status_code} {r.text[:120]}")
    else:
        print("WARNING: no consent recording given; record the speaker's consent before using this voice with customers")

    out = os.path.join(os.path.dirname(HERE), "voice_samples", args.name.replace(" ", "_"))
    os.makedirs(out, exist_ok=True)
    rows = []
    for i, line in enumerate(TEST_LINES, 1):
        for who, p in (("new", pid), ("current", os.environ.get("VOICE_ID", "507e7da2"))):
            raw = say(p, line, *(("raw", "0.5") if who == "new" else ("broadcast", "")))
            if who == "new":
                open(os.path.join(out, f"line{i}.wav"), "wb").write(raw)
            x, xsr = sf.read(io.BytesIO(raw), dtype="float32")
            x = x if x.ndim == 1 else x[:, 0]
            rows.append((who, *pitch_movement(x, xsr)))
    for who in ("new", "current"):
        hz = [r[1] for r in rows if r[0] == who and r[1]]
        mv = [r[2] for r in rows if r[0] == who and r[2]]
        if hz:
            print(f"{who:8s} voice: pitch {int(np.mean(hz))} Hz, pitch movement {np.mean(mv):.2f}  (a flat, AI-like voice is below 2; a lively person is above 2.5)")
    print(f"\nlisten: {out}\nto use it: set VOICE_ID={pid} in start_ria.bat (and VOICE_EFFECT=raw, VOICE_VARIATION=0.5), run record_clips.bat, restart Ria")
    json.dump({"id": pid, "name": args.name}, open(os.path.join(out, "voice.json"), "w"))


if __name__ == "__main__":
    main()
