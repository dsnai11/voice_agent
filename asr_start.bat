@echo off
rem Starts Ria's Hinglish listening service on http://127.0.0.1:3950 (needs VoiceStudio installed: it supplies Python + PyTorch + CUDA).
set HF_HOME=D:\asr_models\hf_cache
"%APPDATA%\VoiceStudio\runtime\project\.venv\Scripts\python.exe" -u "%~dp0asr_server.py"
