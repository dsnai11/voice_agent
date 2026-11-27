@echo off
rem Starts the Ria call app (http://localhost:8000). VoiceStudio, Ollama and the listener (asr_start.bat) must already be running: start_all.bat does all of it.
rem VOICE = the owner's cleaned voice (reference in voice_ref), spoken by tts_server.py (OmniVoice run directly, port 3901; start it with tts_start.bat, VoiceStudio does not need to run). VOICE_ID below only names the voice for the audio cache. Earlier: VoiceStudio profile ac63cfb1 "My voice clean hi" (same voice).
cd /d "%~dp0"
if not defined VOICE_ID set VOICE_ID=ac63cfb1
if not defined COMPANY_XLSX set COMPANY_XLSX=%~dp0..\testdata\company_data.xlsx
set VOICE_EFFECT=
set VOICE_VARIATION=
if not defined VOICE_SPEED set VOICE_SPEED=1.0
if not defined VOICE_NUM_STEP set VOICE_NUM_STEP=24
if not defined VOICE_PITCH_TARGET set VOICE_PITCH_TARGET=0
if not defined VOICE_MIN_PITCH set VOICE_MIN_PITCH=208
if not defined VOICE_PREWARM set VOICE_PREWARM=1
set PREWARM_LANGS=
if not defined VOICE_VERIFY set VOICE_VERIFY=2
if not defined VOICE_PACE set VOICE_PACE=6.4
set VOICESTUDIO_URL=http://localhost:3901
set PORT=8000
set DENOISE=none
set STT_ENGINE=hinglish
set STT_DEBUG=1
set LLM_BASE_URL=http://localhost:11434/v1
set LLM_MODEL=qwen2.5:7b
set VOICE_FORMAT=wav
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -u server.py
