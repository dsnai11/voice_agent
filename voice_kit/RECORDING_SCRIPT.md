# Recording a real voice for Ria

The voice engine copies **how** the reference recording sounds: a calm, smiling, natural phone voice gives a natural Ria; a read-aloud, flat
recording gives a narrator. Ria today is cloned from a narrated clip, which is why she sounds like an AI voice-over.

## Who records

- A woman who **agrees** to her voice being used for Ria (for example someone from the team). She must say the consent sentence below; the
  tool stores it with the voice in VoiceStudio. Never use a recording of someone who has not agreed, or a voice taken from a website or app.

## How to record (phone or laptop is fine)

1. Quiet room, no fan, no TV, no echo (a room with curtains or a bed is better than an empty hall).
2. Phone 15 to 20 cm from the mouth, recording app in normal quality (WAV or M4A).
3. Speak the way she talks to a customer on the phone: friendly, a little smile, natural pauses. **Do not read like news.**
4. Record each part separately; it is fine to repeat a line until it sounds natural. Total about 20 to 30 seconds for the voice, plus the
   consent sentence as its own file.

## Part 1: the voice (say it like a real call, about 25 seconds)

> जी नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस से। अच्छा जी, समझ गई। आपको कितने का लोन चाहिए, लगभग? कोई बात नहीं,
> आप आराम से बताइए। हाँ जी, ये तो बिल्कुल हो जाएगा। बस आपकी थोड़ी सी जानकारी चाहिए, फिर हमारी टीम आपको कॉल कर लेगी। ठीक है?

(The tool needs this exact text as the transcript. If she changes a word, change it in `--text` too.)

## Part 2: consent (separate file)

> मैं, *[पूरा नाम]*, अपनी मर्ज़ी से अपनी आवाज़ लक्ष्मी इंडिया फाइनेंस की कॉलिंग असिस्टेंट "रिया" के लिए इस्तेमाल करने की अनुमति देती हूँ।

## Make the voice

```powershell
cd "D:\Voice Agent Model\voice_agent"
.\.venv\Scripts\python.exe make_voice.py --audio "D:\path\voice.wav" --consent "D:\path\consent.wav" --speaker "Full Name" --name "Ria Human"
```

The tool cleans the recording, creates the voice in VoiceStudio, says five Ria lines in the new voice (in `voice_samples\<name>\`) and prints
the voice id. If it sounds good, put that id in `start_ria.bat` (`VOICE_ID=...`), run `record_clips.bat`, and restart.
