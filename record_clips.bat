@echo off
rem Re-records the fixed phrases (greeting, closing, "please repeat" ...) with the SAME voice settings as start_ria.bat. Run it after changing a line in clips.py. VoiceStudio must be running.
cd /d "%~dp0"
if not defined VOICE_ID set VOICE_ID=507e7da2
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" clips.py
