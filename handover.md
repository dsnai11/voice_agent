# Handover: Ria, Hinglish AI calling agent for Laxmi India Finance Limited

Last updated: 19 Nov 2026 (see section 0 for what changed). This replaces the 18 Nov 2026 version. Read this file first, then `KAGGLE.md` (how to run on Kaggle's free GPU).

## 0. Update 19 Nov 2026: what is new and how to run it on the laptop (RTX 5060, 8 GB)
**Why:** the stock listening model wrote Urdu script for Hindi (or translated wrongly in English mode), and the 7B model could not run a call by itself. Both are fixed.
- **Hinglish listening service** (`asr_server.py`, `asr_start.bat`): runs `Oriserve/Whisper-Hindi2Hinglish-Apex` (Apache-2.0, ~1.6 GB, Roman Hinglish output, ~0.3 s per sentence) on port 3950, using VoiceStudio's Python (it already has PyTorch + CUDA + transformers). Model files live in `D:sr_models\Whisper-Hindi2Hinglish-Apex` (download with `huggingface_hub.snapshot_download`; not in git). Boosts quiet audio before listening. Ria uses it with `STT_ENGINE=hinglish`. `stt.py` has `transcribe_hinglish` plus `fix_terms` (e.g. "pay day launch" -> "payday loan") and a filter for Whisper's phantom words on silence. The old Hindi hint prompt was removed: it turned correct audio into garbage.
- **Guided call flow** (`flow.py`, on by default, `FLOW=0` switches it off): code asks one question at a time (name, loan type, amount, job, income, city, existing loans, phone, consent, callback time), parses exact values (amounts such as "dhai lakh", phone digits, names), answers questions from the approved reply bank, reads the mobile number back for a yes/no before trusting it, and returns `None` for existing-customer / complaint / collections topics so the full assistant (LLM + CRM) handles them. Stopping needs an explicit refusal ("mat karna", "band karo", "DND"). The callback time is said back ("... आधे घंटे बाद कॉल करेगी"). `python flow.py` is a typed test.
- **Speed:** Ollama must run with a bigger context or each reply takes 14 to 30 s. Start it like this (PowerShell): `$env:OLLAMA_MODELS="D:\ollama_models"; $env:OLLAMA_CONTEXT_LENGTH="6144"; $env:OLLAMA_NUM_PARALLEL="1"; $env:OLLAMA_MAX_LOADED_MODELS="1"; $env:OLLAMA_FLASH_ATTENTION="1"; $env:OLLAMA_KV_CACHE_TYPE="q8_0"; $env:OLLAMA_KEEP_ALIVE="24h"; Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -ArgumentList serve -WindowStyle Hidden`. The Ollama tray app ignores `OLLAMA_MODELS`, so start `serve` yourself. `OLLAMA_NUM_PARALLEL=1` matters most on an 8 GB card: without it the language model writes about 13 words/s (memory spills), with it about 66. Replies are then 2 to 3 s; flow replies are instant. `server.py` pre-records ~195 common sentences at start-up (`flow.static_sentences()`), shows the text together with the first audio, and uses `TURN_SILENCE_S=1.0`, `CHUNK_SILENCE_S=0.5`. When speech is heard but not understood, Ria plays one of 5 "please say that again" clips.
- **Free talk (added 19 Nov):** after the form (or in the middle of it), questions about the company, loan types, CIBIL, EMI, office, small talk and "I want to talk about something else" are answered from approved bank entries (8 new topics) instantly; anything else goes to a short grounded language-model answer (`flow.Flow._free`, uses `knowledge/ria_facts.txt` + `knowledge/company_info.txt` = public website facts, **needs Compliance sign-off**). Short replies ("ok", "theek hai", "chalo aage chalo") count as agreement. The reply is written once per turn from everything said (pauses do not split a sentence); while a phone number is half said she waits `PHONE_SILENCE_S` (3.5 s) and remembers the digits; "double 9" works. Saying goodbye ("call kaato", "bye") ends the call after the closing thank-you and the page hangs up by itself.
- **Questions in the flow (industry-standard, 19 Nov):** name, loan type, amount, purpose, job, income, city, existing loans, existing EMI per month (only if loans exist), mobile number (read back), consent, callback time. Every question accepts one word, two words or a full sentence (`slot_tests` style check: 84 of 84 variants pass). Objection answers added: interest too high, why do you need my details. Research notes: public NBFC/BFSI voice-agent write-ups agree on this BANT-style set (purpose, amount, job, existing EMIs, city) in under 3 minutes and warn against promising rates. The greeting and every goodbye say the company name; the page waits until all audio has played before it hangs up.
- **Finance and banking knowledge (19 Nov, evening):** `knowledge/general_finance.txt` (general, public facts: EMI, flat vs reducing, APR, credit score and free reports, RBI borrower protections, KYC, NACH, UPI/NEFT, FD/RD, DICGC, fraud reporting) is read by the free-answer path, and ~30 curated Hinglish answers for the same topics sit in `reply_bank.json` (92 topics). Bank entries can now carry `require` / `forbid` word lists so "NACH kya hota hai" can never get the EMI answer; entries with a matched `require` are preferred over generic ones. Questions Ria cannot know (company turnover, today's repo rate) get an honest "mujhe pakka nahi pata, team confirm karegi"; investment and tax advice is declined; non-finance topics get a polite redirect. Any AI-written free answer passes `Flow._guard_ok` first (no numbers outside the approved text and the caller's own words, no promises, no list formatting, 9-second limit) and falls back to the honest line. Research finding: there is no public Hinglish banking call dataset (BANKING77 is English only, Skit-S2I is Indian-English speech with 14 intents), so the answers are written in-house and checked with `train/qa_tests.py`, `train/slot_tests.py` and `train/test_replybank.py` (61 cases).
- **Everything on D:** project, `.venv`, models (`D:\ollama_models`, `D:sr_models`, `D:oice studio`), test data and logs (`D:\Voice Agent Model	estdata`, `logs`), pip cache (`PIP_CACHE_DIR=D:\pip_cache`). `db.py` now defaults the data file to the project folder instead of `C:\Voice-agent`.
- **C: drive freed (19 Nov, late):** VoiceStudio's runtime (the voice engine, 18.6 GB) now lives in `D:\VoiceStudio_data\runtime` and Ollama's program files (3 GB) in `D:\Ollama_program`. On C: the old locations (`%APPDATA%\VoiceStudio\runtime` and `%LOCALAPPDATA%\Programs\Ollama`) are NTFS junctions (links) to D:, so the apps and `asr_start.bat` find everything exactly where they expect it. **D: must be present for the voice agent to start.** If an app is re-installed or updated and recreates a real folder at the old path, move it to D: again the same way: stop the app, `robocopy /E` the folder, check that every file matches, rename the old folder, create the link with `New-Item -ItemType Junction`, test, then delete the old folder. Still on C: Ollama's auto-downloaded installer `%LOCALAPPDATA%\Ollama\updates_v2` (1.7 GB, safe to delete by hand) and the small VoiceStudio program folder in `C:\Program Files`.
- **End-to-end check:** `python train/call_test.py` (app, VoiceStudio and the listener running) connects like the call page, speaks two Hindi sentences and checks the greeting audio, what was heard, the filled form and the spoken answers.
- **Mic:** the call page shows a live mic level bar; `?raw=1` turns off the browser's voice processing. A muted Windows microphone gives pure silence (it happened here: set Input volume to 80 to 100 and unmute).
- **Debug:** `STT_DEBUG=1` saves every chunk of caller audio and what was heard to `calls/stt_debug/` (git-ignored) so listener settings can be compared on real voices.
- **Start order after a reboot:** VoiceStudio app (port 3900), Ollama (command above), `asr_start.bat` (port 3950), then:
  `$env:PORT="8000"; $env:DENOISE="none"; $env:STT_ENGINE="hinglish"; $env:LLM_BASE_URL="http://localhost:11434/v1"; $env:LLM_MODEL="qwen2.5:7b"; $env:VOICE_ID="<id of the imported Hindi Narrator>"; $env:VOICE_FORMAT="mp3"; $env:VOICE_NUM_STEP="12"; python server.py`. Import the voice once with `POST /marketplace/import` (file `Hindi_Narrator.omnivoice`); its id differs per VoiceStudio install.
- **Measured here:** `llm_eval.py` scores 6/13 on qwen2.5:3b and 8/13 on qwen2.5:7b. The misses are tool-calling (the model does not fill the form by itself): the flow now does that in code. Next ideas: tune the flow on real call logs, test a larger model on the paid GPU, grow the reply bank, add Devanagari-aware parsing for callers whose speech comes back in Devanagari.
- **Disk:** keep big files on D: (C: is nearly full). Ollama models: `D:\ollama_models`; listening model: `D:sr_models`; VoiceStudio models: `D:oice studio`.

## 1. What this is
A web app (TeleCMI telephony comes later). A caller opens `http://localhost:8000`, presses **Call**, and talks by voice to **Ria**, a female AI assistant. Ria handles **outbound and inbound** calls for three digital products: **payday loan, salary loan, personal loan**, and (for now) takes overdue-payment calls only as "schedule a callback". She speaks **Hinglish**: everyday Hindi in Devanagari with English words (लोन, ईएमआई, सैलरी, डॉक्यूमेंट), never formal Hindi. If the caller speaks English, she answers in English. While they talk an enquiry form fills itself in, existing customers see loan details as cards, and every call becomes a lead or a query.

```
Browser mic -> server.py (WebSocket /ws/call)
  -> denoise.py -> stt.py (speech to text) -> replybank.py (best approved replies) -> brain.py (LLM writes the reply + calls tools)
        tools: update_form, get_account_details (crm.py), request_callback (db.py), finish_call, verify_identity, find_customer
  -> voice.py (VoiceStudio TTS, sentence by sentence) / clips.py (recorded phrases) -> browser speaker
  -> db.py + tickets.py save: Excel sheets + calls/<call_id>.json
```

The user is not a developer. Explain plainly, say what is and is not verified, ask before building each new step, and talk in English.

## 2. Decisions the user has made (do not re-open)
- **No Gemini API.** The LLM is a small/medium open model behind an OpenAI-compatible endpoint (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`), served by Ollama. Keep it swappable to any GPU.
- **Kaggle's free GPU is for training/fine-tuning and testing only.** Buy a GPU only when the model is ready for telephony.
- Hindi **Narrator** voice (VoiceStudio) is the default voice. Target: voice reply in 1 to 2 seconds (not reached yet).
- Replies are **Hinglish, not proper Hindi**. Fake data only on Kaggle.
- **Collections and late fees, for now:** Ria never states overdue amounts, late fee or bounce charge figures, waivers, settlements, extensions or plans. She says the collections team will handle it, asks the day and time (calling hours 8 AM to 7 PM), saves it with `request_callback`, and confirms the slot. No call transfer yet (no telephony).
- **Payday and salary loan terms are unknown.** Ria says the team will confirm, collects the need and salary date, offers a callback, and never reuses personal loan terms.
- Questions are not fixed: more questions and replies will be added later by editing the reply bank.

## 3. Environment
- Windows 11 laptop, **CPU only**, 16 GB RAM, Python **3.14.8**. Project `C:\Voice-agent`. VoiceStudio `C:\Users\asha.kanwar\VoiceStudio` (API `http://localhost:3900`, default engine k2-fsa/OmniVoice).
- Secrets: never print or ask for keys in chat. `HF_TOKEN` must be a Kaggle Secret. A temporary VoiceStudio key was pasted in chat earlier: treat it as exposed and rotate it.
- Packages: fastapi, uvicorn, websockets, openpyxl, numpy, requests, openai, soundfile, sounddevice, faster-whisper (fallback listener), noisereduce.

## 4. How to run
Local (CPU, slow; for code testing):
```powershell
cd C:\Users\asha.kanwar\VoiceStudio; bun run dev      # tab 1
cd C:\Voice-agent; python server.py                    # tab 2, open http://localhost:8000
```
Real speed needs a GPU: follow `KAGGLE.md` ("Complete flow"). Short version: upload `kaggle\ria_app.zip` as a Kaggle dataset, start GPU T4 x2 with internet, unzip, `cp gpu_server.py`, run it (`LLM_BACKEND=ollama`; `ACCEPT_LICENCES=yes` only once the company agrees to the voice-model licences). It starts Ollama (models on `/kaggle/temp`, because `/kaggle/working` is capped at 20 GB), VoiceStudio, a cloudflared tunnel and the app.

## 5. Files
| File | Role |
|---|---|
| `server.py` | FastAPI app + WebSocket call sessions; chunked listening, turns, saving. |
| `brain.py` | `Call` class: prompt (`_BASE_RULES` + `knowledge/ria_facts.txt`), tool loop, form state, identity logic. Calls `replybank.hint()` on each caller turn (enquiry mode). |
| `replybank.py` | Splits what the caller said into chunks, matches each against `knowledge/reply_bank.json` (script- and spelling-independent consonant skeleton, no model), returns approved replies as guidance to the LLM. `python replybank.py "sentence"` tests one line. |
| `knowledge/reply_bank.json` | **Editable** bank: 55 topics, about 350 example phrasings, Hinglish reply and an action note each. This is where questions and replies are added or updated. |
| `knowledge/ria_facts.txt` | The only facts Ria may state (company, toll-free 18001217747, hours, personal loan rules/charges, complaint path, safety, collections rule). Late fee amounts were removed on purpose. |
| `knowledge/products.md` | Longer tagged knowledge draft ([SITE]/[CONFLICT]/[TYPICAL]/[FILL-IN]); not yet approved by Compliance. |
| `flow.py` | Guided new-loan call flow (see section 0): exact values, one question at a time, approved answers. |
| `asr_server.py`, `asr_start.bat` | Local Hinglish listening service (port 3950, GPU). |
| `forms.py`, `crm.py`, `db.py`, `tickets.py` | Form validation, CRM connector (demo Excel or REST, `>>> ADAPT` spots), data layer, lead/query rules. |
| `voice.py`, `clips.py`, `stt.py`, `listen.py`, `denoise.py` | TTS client (`speakable`, `sanitize_reply`), recorded phrases, speech to text (`STT_ENGINE` api/gemini/whisper), speech detection, noise removal. |
| `llm_eval.py` | 13 behaviour cases against the configured LLM. |
| `train/seed_conversations.jsonl` | 27 reviewed Hinglish training conversations. `check_examples.py` validates them (27/27 pass). |
| `train/finetune.py` | QLoRA fine-tune (Kaggle). `compare_models.py` scores a model on 12 questions. `test_replybank.py` checks the reply bank (39/39 pass). |
| `kaggle/gpu_server.py`, `kaggle/make_zip.py` | Kaggle start-up script; `make_zip.py` builds `kaggle\ria_app.zip` (code, web, fake CRM, voice, knowledge, train). |
| `KAGGLE.md` | Kaggle flow and troubleshooting. `web/index.html`: the page. |

## 6. Settings (environment variables)
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `VOICESTUDIO_URL`, `VOICESTUDIO_API_KEY`, `VOICE_ID`, `VOICE_FORMAT`, `VOICE_NUM_STEP`, `STT_ENGINE`, `DENOISE`, `CHUNK_SILENCE_S` (0.7), `TURN_SILENCE_S` (1.6; plan to shorten), `MAX_CALL_S`, `DATA_BACKEND`, `COMPANY_XLSX`, `CRM_BACKEND`, `CRM_XLSX`, `CRM_API_URL`, `CRM_API_KEY`, `CRM_VERIFY` (`phone` default, `dob_last4` stricter), `HOST`, `PORT`. Kaggle script: `LLM_BACKEND` (ollama default), `LLM_PULL`, `ACCEPT_LICENCES`, `OLLAMA_DIR`, `HF_HOME`.

## 7. Behaviour rules (settled)
- AI disclosure when asked; identity check before any account data; consent before callback; never ask for OTP, PIN, CVV or password; honour stop-calling; never promise approval, amounts, rates or timing (24 to 48 hours is only "usually").
- Every call creates a lead or a query; the mobile number is the customer ID; account data shown as masked cards, audited, removed at call end.
- Replies: 1 to 3 short sentences, one question at a time, digits converted to Hindi words by code.
- Reply bank flow: chunk the speech, match each chunk, give the LLM the approved meaning + action, LLM says it fresh in Hinglish. No match means normal rules and facts. Console prints `[reply bank] [ids]` per matched turn.

## 8. Model findings so far
Qwen2.5-3B (base and fine-tuned): gibberish Hindi, unusable. Qwen2.5-7B-Instruct: 5/12 on `compare_models.py`. Fine-tuning fixes rule-following, not fluency; fluency needs a bigger model. Untested candidates: Qwen3-14B via Ollama (needs tool support), Sarvam-M 24B (Hindi-focused, large), Gemma-2-9b-it (the user said access was rejected; Kaggle Models input is the unresolved workaround), Llama-3.1-8B (gated). A larger model on the paid GPU may be required. Nothing has passed yet; no live small-model call has been completed.

## 9. Known issues and limits
- Kaggle sessions are temporary: disk wiped, licences must be re-accepted, ASR model reinstalled (the script now handles ASR and licences). `/kaggle/working` is 20 GB; models go to `/kaggle/temp`. Two T4s: the notebook kernel can hold GPU 0, run tests with `CUDA_VISIBLE_DEVICES=1`. `peft` needs `torchao` uninstalled. Newer `transformers` has no `warmup_ratio`.
- The new `gpu_server.py` and the reply bank have **never run on Kaggle**; the reply bank is only tested offline (39 phrasings written by the assistant). Real call transcripts will reveal gaps.
- Reply bank matches words, not meaning: a miss gives no guide (safe); a rare wrong match is possible (the LLM is told to ignore items that do not fit). Example: "loan kitne mahine ka hoga" matches only the EMI topic until tenure examples are added.
- VoiceStudio serves one request at a time; speed on CPU is far too slow for real-time (75 to 104 s per sentence). Streaming reply path not built.
- Real CRM not connected. Letters in spoken account numbers can be lost. No tool-call examples in the training data yet.
- Gemini terms: not used for training data; check before ever using Gemini-generated data.

## 10. Pending (in order)
1. User uploads the new `kaggle\ria_app.zip`, re-runs the Kaggle cells (free disk, Ollama on `/kaggle/temp`, pull `qwen2.5:7b`), copies the new `gpu_server.py`, runs the app, does the first live call and pastes the logs (including `[reply bank]` lines and turns that matched nothing).
2. Run `llm_eval.py` on candidate models (qwen3:14b etc.); decide the model; consider Sarvam-M or larger on the paid GPU.
3. Grow the reply bank and the training set from real calls and reviewed drafts (target a few hundred reviewed conversations); add tenure/other missing examples; keep the checker passing.
4. **Needed from the business:** payday and salary loan terms; calling hours, consent source and DND policy; Compliance resolution of conflicts (tenure, bounce charge, prepayment %); RBI registration number; confirm grievance officer names are current; whether collections will later be handled by Ria (needs a compliance review; recovery rules proposed: 8 AM to 7 PM, borrower only, no threats, hardship to a human, disputes stop collection).
5. Build: streaming reply path, shorter `TURN_SILENCE_S`, lead table/campaign queue, real CRM, TeleCMI telephony (confirm two-way audio first; outbound needs TRAI/DND compliance), HTTPS and login before public exposure, privacy review, payment-link/SMS if wanted.
6. Open security choice: phone-only identification lets anyone who knows a number hear loan details. Options: keep, name match, SMS one-time code, `CRM_VERIFY=dob_last4`.
7. Housekeeping: four test callback rows for 9990001111 in the real `callbacks` sheet (delete?); do not run `python crm.py --make-demo` without asking (overwrites `crm_demo.xlsx`).

## 11. Testing safely
Never test against the real `company_data.xlsx` (copy to a temp folder, set `COMPANY_XLSX`). Use `PORT=8001`. Fake demo customers: Priya Verma 9990002222 (1990-07-21, ends 9012), Rahul Sharma 9990001111 (1985-03-12, ends 5678), Amit Singh 9876543210 (1988-11-02, ends 7341). Checks: `python train/check_examples.py`, `python train/test_replybank.py`, `python llm_eval.py`.
