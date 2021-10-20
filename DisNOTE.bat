cd /d %~dp0

python -m pip install --upgrade pip > stdout.txt
pip install tensorflow inaSpeechSegmenter pydub ffmpeg-python SpeechRecognition  > stdout.txt

python src/all.py %* 2> stderr.txt
PAUSE