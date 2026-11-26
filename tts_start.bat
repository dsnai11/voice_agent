@echo off
rem Starts Ria's own voice server on http://127.0.0.1:3901 (uses VoiceStudio's Python for PyTorch + OmniVoice; VoiceStudio itself does not need to run).
set HF_HOME=D:\asr_models\hf_cache
set TTS_STEPS=24
"%APPDATA%\VoiceStudio\runtime\project\.venv\Scripts\python.exe" -u "%~dp0tts_server.py"
