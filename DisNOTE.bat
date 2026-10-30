cd /d %~dp0

if not exist src\.venv\Scripts\python.exe py -m venv src\.venv

src\.venv\Scripts\python.exe -m pip install --upgrade pip > stdout.txt
src\.venv\Scripts\python.exe -m pip install mutagen requests faster-whisper==1.2.1 torch==2.8.0 python-dateutil==2.8.2 janome==0.5.0 > stdout.txt
rem src\.venv\Scripts\python.exe -m pip install git+https://github.com/openai/whisper.git > stdout.txt
src\.venv\Scripts\python.exe -m pip freeze > freeze_develop.txt

src\.venv\Scripts\python.exe src/all.py --files %* 2> stderr.txt
PAUSE