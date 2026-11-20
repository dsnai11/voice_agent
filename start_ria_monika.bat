@echo off
rem Starts Ria with the ONLINE ElevenLabs voice "Monika Sogam" instead of the offline VoiceStudio voice. Needs internet and your own ElevenLabs API key (paid plan for Voice Library voices).
rem One time, in PowerShell:   setx ELEVENLABS_API_KEY "your-key"      then open a new terminal.   Optional: setx ELEVENLABS_VOICE_ID "id-from-the-voice-page"
rem The listener (asr_start.bat) and Ollama still run on this PC; only the spoken voice is online. Switch back by using start_ria.bat.
set VOICE_ENGINE=elevenlabs
set ELEVENLABS_VOICE_NAME=Monika Sogam
call "%~dp0start_ria.bat"
