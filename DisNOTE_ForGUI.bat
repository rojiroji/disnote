cd /d %~dp0

py -m pip install --upgrade pip > stdout.txt
py -m pip install inaSpeechSegmenter ffmpeg-python SpeechRecognition mutagen requests > stdout.txt
rem py -m pip install git+https://github.com/openai/whisper.git > stdout.txt
py -m pip freeze > freeze_develop.txt

py src/all.py %* 
