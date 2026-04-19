@echo off
REM Build iRacingCommentator.exe (onefile, windowed)
setlocal

echo [*] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist iRacingCommentator.spec del /q iRacingCommentator.spec

echo [*] Running PyInstaller...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "iRacingCommentator" ^
    --hidden-import irsdk ^
    --hidden-import pyirsdk ^
    --hidden-import elevenlabs ^
    --hidden-import elevenlabs.client ^
    --hidden-import pygame ^
    --hidden-import openai ^
    --hidden-import anthropic ^
    --hidden-import google.generativeai ^
    --hidden-import edge_tts ^
    --hidden-import aiohttp ^
    --hidden-import pyttsx3 ^
    --hidden-import pyttsx3.drivers ^
    --hidden-import pyttsx3.drivers.sapi5 ^
    --hidden-import tts_sapi ^
    --hidden-import tts_edge ^
    --hidden-import tts_elevenlabs ^
    --hidden-import facts_provider ^
    --hidden-import templates ^
    --hidden-import updater ^
    --add-data "data;data" ^
    --collect-submodules pyttsx3 ^
    --collect-submodules edge_tts ^
    --collect-submodules aiohttp ^
    --collect-submodules elevenlabs ^
    --collect-submodules openai ^
    --collect-submodules anthropic ^
    --collect-submodules google.generativeai ^
    --collect-submodules google.ai ^
    --collect-submodules httpx ^
    --collect-submodules httpcore ^
    --collect-data certifi ^
    --collect-data elevenlabs ^
    --collect-data openai ^
    --collect-data anthropic ^
    --collect-data google.generativeai ^
    main.py

if errorlevel 1 (
    echo [!] Build failed.
    exit /b 1
)

echo.
echo [+] Build OK: dist\iRacingCommentator.exe
dir dist\iRacingCommentator.exe | findstr iRacingCommentator.exe

endlocal
