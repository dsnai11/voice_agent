# Running Ria's models on a Kaggle GPU

Status (12 Nov 2026): code is ready and the default (Gemini + local VoiceStudio) still works. **The Kaggle script has not been run on Kaggle yet**, so expect small fixes on the first run. Use fake or test data only on Kaggle.

## The idea
Two places, joined by web addresses:

| Stays on your laptop / app server | Runs on the GPU (Kaggle now, any GPU later) |
|---|---|
| `server.py` (calls), `brain.py` (conversation rules), forms, CRM, leads, Excel/DB, `web/` page, telephony later | VoiceStudio: Ria's voice **and** listening. Ollama: the small language model. |

The GPU side holds no customer records. Each request carries only the sentence or audio of that moment.

Moving to another GPU = start the same two servers there and change **five settings**. No code change.

| Setting | Meaning | Default |
|---|---|---|
| `VOICESTUDIO_URL` | where the voice and listening server is | `http://localhost:3900` |
| `VOICESTUDIO_API_KEY` | key for a remote VoiceStudio | none |
| `LLM_BASE_URL` | where the language model is (any OpenAI-style server) | Gemini |
| `LLM_MODEL` | model name | `gemini-3.5-flash-lite` |
| `STT_ENGINE` | `api` = listen on the GPU server, `whisper` = laptop, `gemini` = Google | `gemini` |

## What was reused (no re-development)
- VoiceStudio already has an OpenAI-style speech **and** transcription API, an API-key mode for remote use, and Tesla T4 notes (about 1 s per sentence once the model is cached, versus 75 to 104 s on your CPU). Kaggle's T4 is the same GPU.
- Its Colab notebook is the model for `kaggle/gpu_server.py`.
- Ria's app code is unchanged except: `brain.py` (model address and key from settings), `voice.py` (key header), `stt.py` (`transcribe_api`), `server.py` (`STT_ENGINE=api`, health check key). `llm_eval.py` is the Hindi test set.

## Steps
**A. One-time, on Kaggle** (kaggle.com, phone-verified account)
1. New notebook. Settings: Accelerator = GPU (T4 x2 or P100), Internet = On.
2. Cell 1: `!git clone --depth 1 https://github.com/debpalash/VoiceStudio /kaggle/working/VoiceStudio`
3. Upload `kaggle/gpu_server.py` to the notebook, then cell 2: `%run gpu_server.py install` (about 10 minutes).
4. Cell 3: `%run gpu_server.py start`. It prints the five settings.

**B. On the laptop** (PowerShell; paste the lines the notebook printed, then)
```powershell
cd C:\Voice-agent
python llm_eval.py            # Hindi test set against the small model
python server.py              # open http://localhost:8000 and make a test call
```
Check `http://localhost:8000/api/health` first: it should show VoiceStudio reachable.

**C. Decide**
1. Compare `llm_eval.py` scores with Gemini's (10 of 11, the miss being English-speaking callers).
2. Try other models: set `LLM_PULL` in the notebook (for example a different size) and run the test set again.
3. Time a full sentence: speech, listening and reply. Compare with the 75 to 104 s on CPU.
4. Only when a model passes: remove Gemini from the default.

## Known limits of Kaggle
- Sessions are temporary and GPU hours per week are capped. After a restart, run step 4 again: the two addresses change, so the laptop settings must be updated.
- Checks to make before relying on it: Kaggle's terms for this use, and whether the voice server fits alongside the model in GPU memory.
- The language-model address has **no key** (the quick tunnel is only an unguessable web address). That is acceptable for test data only. Before any real data, put it behind a key (a small proxy or a private network such as Tailscale) on the production GPU.
- Not yet solved: reply speed with chunked listening on GPU, several callers at once (VoiceStudio serves one voice request at a time), and an always-on server for telephony. Those need the paid GPU.

## Faster setup: the whole app on Kaggle (13 Nov 2026)
Every stage talks over `localhost` on the GPU machine; only the browser crosses the internet, through one HTTPS tunnel.
1. On the laptop: `python kaggle\make_zip.py` makes `kaggle\ria_app.zip` (code, fake demo customers, empty data file, the Hindi Narrator voice; no call records or keys).
2. On Kaggle: Add Input -> Upload -> New Dataset -> choose `ria_app.zip` (keep the dataset private).
3. Run, in order: the clone cell, `%%writefile /kaggle/working/gpu_server.py`, `%run /kaggle/working/gpu_server.py install`, `%run /kaggle/working/gpu_server.py app`.
4. Open the address it prints in Chrome on the laptop (headphones), press Call. Timings: `!tail -f /kaggle/working/logs/ria_app.log`.
The older two-tunnel setup (app on the laptop) is still available as `... gpu_server.py start`.

## Licences (first run on a new server)
VoiceStudio refuses to speak (HTTP 403 `model_licence_required`) until a person accepts the licences of `k2-fsa/OmniVoice` and `eustlb/higgs-audio-v2-tokenizer`. Read the terms with `GET /models/licenses/details/<repo>` on the voice server and accept with `POST /models/licenses/accept` (`repo_id`, `fingerprint`, `accepted: true`) only after your company has decided the licence allows this use. Acceptance is stored in the server's data folder, so on Kaggle it must be repeated after each session reset.

Measured on Kaggle (12 Nov 2026): first speech request 68 s (model load), then 1.3 s for a two-sentence reply, mp3, num_step 12.

## Complete flow (current, 17 Nov 2026)
`kaggle\make_zip.py` now packs `gpu_server.py`, the facts file (`knowledge/ria_facts.txt`) and the training files into `ria_app.zip`. On a fresh session: copy the dataset, `install`, set `ACCEPT_LICENCES=yes` only after your company agrees, set `LLM_BACKEND` (`gemini` or `ollama`), then `app`. The script installs the listening model and waits for it. Language model results so far: Qwen2.5-3B and 7B score 2 and 5 of 12 on `train/compare_models.py`, so use `LLM_BACKEND=gemini` for live tests until a small model passes.

## Next after this works
Lead table and campaign queue (Phase 2 in the earlier plan), then knowledge-file retrieval for loan Q&A, then telephony.
