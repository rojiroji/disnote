cd /d %~dp0

py -m pip install --upgrade pip > stdout.txt
py -m pip install inaSpeechSegmenter ffmpeg-python SpeechRecognition mutagen requests > stdout.txt

py src/all.py %* 2> stderr.txt
PAUSE