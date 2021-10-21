# DisNOTE
録音からテキストを書き出すツール"DisNOTE"

# 使い方
Python 3.9.x で動作確認
> pip install inaSpeechSegmenter ffmpeg-python SpeechRecognition mutagen requests 
> 
> python src/all.py \<audiofile1\> \<audiofile2\> \<audiofile3\> ...

PATHを通した先に[ffmpeg](https://ffmpeg.org/)を配置しておくこと。

# 使い道
動画での説明（どちらも内容は同じ）
* [ニコ動](https://www.nicovideo.jp/watch/sm39257003)
* [Youtube](https://youtu.be/pCebMJgtVBM)

# フリーソフトとして
プログラミングの知識がない人向けにWindows用フリーソフトとして公開している。

[公開先](https://roji3.jpn.org/disnote/)

Pythonとffmpegを用意した上で、DisNOTE.batに音声ファイルをドラッグ＆ドロップすることで起動する。
インストール方法などは上記の動画で説明している。

Readme.txtはフリーソフトとしてのDisNOTEのReadme、README.md（このファイル）は開発者向けのReadmeである。

# 認識APIについて
内部で[Speech API](https://console.cloud.google.com/apis/library/speech-json.googleapis.com?project=black-dragon-324616)を呼び出している。
そのため、起動する前にSpeech APIの利用規約を参照すること。
* [Google Speech API Terms of Service](https://console.cloud.google.com/tos?id=speech&project=black-dragon-324616&supportedpurview=project)
* [Google APIs Terms of Service](https://console.cloud.google.com/tos?id=universal&project=black-dragon-324616&supportedpurview=project)

Speech APIについては次の記事を参考にした。https://qiita.com/lethe2211/items/7c9b1b82c7eda40dafa9

[Speech-to-Text](https://cloud.google.com/speech-to-text)とは別物（っぽい）ので注意。

# Pull requestについて
Wikiに設計メモ書いてるので参考にしてください。待ってる。
