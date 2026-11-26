@echo off
rem Re-records the fixed phrases (greeting, closing, "please repeat" ...) with the SAME voice settings as start_ria.bat. Run it after changing a line in clips.py. VoiceStudio must be running.
cd /d "%~dp0"
if not defined VOICE_ID set VOICE_ID=ac63cfb1
set VOICE_EFFECT=
set VOICE_VARIATION=
if not defined VOICE_SPEED set VOICE_SPEED=1.0
if not defined VOICE_NUM_STEP set VOICE_NUM_STEP=24
if not defined VOICE_PITCH_TARGET set VOICE_PITCH_TARGET=0
if not defined VOICE_MIN_PITCH set VOICE_MIN_PITCH=208
if not defined VOICE_VERIFY set VOICE_VERIFY=2
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" clips.py
