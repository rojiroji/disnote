@echo off
cd /d "%~dp0"

src\.venv\Scripts\python.exe -m pip install --upgrade pip > stdout.txt
if errorlevel 1 exit /b 1
src\.venv\Scripts\python.exe -m pip install ffmpeg-python mutagen requests faster-whisper==1.2.1 torch==2.8.0 python-dateutil==2.8.2 > stdout.txt
if errorlevel 1 exit /b 1

src\.venv\Scripts\python.exe src\all.py %*
exit /b %errorlevel%
