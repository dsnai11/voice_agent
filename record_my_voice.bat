@echo off
rem Opens the on-screen-script voice recorder at http://localhost:3910. Recordings are saved to D:\Voice Agent Model\voice_recordings (nothing leaves this PC).
cd /d "%~dp0"
".venv\Scripts\python.exe" voice_kit\recorder.py
