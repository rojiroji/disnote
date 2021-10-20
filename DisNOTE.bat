cd /d %~dp0

py -m pip install --upgrade pip > stdout.txt
py -m pip install tensorflow inaSpeechSegmenter pydub ffmpeg-python SpeechRecognition mutagen > stdout.txt

py src/all.py %* 2> stderr.txt
PAUSE