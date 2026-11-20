@echo off
rem Starts the Ria call app (http://localhost:8000). VoiceStudio, Ollama and the listener (asr_start.bat) must already be running: start_all.bat does all of it.
rem VOICE_ID = a voice profile id in THIS PC's VoiceStudio: 507e7da2 = Hindi Narrator (the original voice, in use); ebf5ee9d = Ria Natural (a more expressive designed voice, kept for later). Another PC has other ids.
cd /d "%~dp0"
if not defined VOICE_ID set VOICE_ID=507e7da2
if not defined COMPANY_XLSX set COMPANY_XLSX=%~dp0..\testdata\company_data.xlsx
set PORT=8000
set DENOISE=none
set STT_ENGINE=hinglish
set LLM_BASE_URL=http://localhost:11434/v1
set LLM_MODEL=qwen2.5:7b
set VOICE_FORMAT=mp3
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -u server.py
