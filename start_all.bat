@echo off
rem One click: starts everything Ria needs, in the right order. Drive D: must be connected (the voice engine and the models live there).
rem 1 VoiceStudio (voice) -> 2 Ollama (language model) -> 3 the Hinglish listener -> 4 the Ria app. Then open http://localhost:8000
set OLLAMA_MODELS=D:\ollama_models
set OLLAMA_CONTEXT_LENGTH=6144
set OLLAMA_FLASH_ATTENTION=1
set OLLAMA_KV_CACHE_TYPE=q8_0
set OLLAMA_KEEP_ALIVE=24h
set OLLAMA_NUM_PARALLEL=1
set OLLAMA_MAX_LOADED_MODELS=1
echo Starting the voice server ...
start "Ria voice" /min cmd /c "%~dp0tts_start.bat"
echo Starting Ollama ...
start "Ollama" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
echo Waiting for the voice engine and the language model (about 40 seconds) ...
timeout /t 40 /nobreak >nul
echo Starting the listener ...
start "Ria listener" /min cmd /c "%~dp0asr_start.bat"
timeout /t 30 /nobreak >nul
echo Starting the Ria app ...
start "Ria app" /min cmd /c "%~dp0start_ria.bat"
echo Done. In about a minute open http://localhost:8000 (first greeting can take 15 seconds).
timeout /t 5 >nul
