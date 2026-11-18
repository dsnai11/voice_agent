# Handover: Ria, Hinglish AI calling agent for Laxmi India Finance Limited

Last updated: 18 Nov 2026. This replaces the 29 Oct 2026 version. Read this file first, then `KAGGLE.md` (how to run on Kaggle's free GPU).

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
