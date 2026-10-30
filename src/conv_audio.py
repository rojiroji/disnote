import os
import sys
import common
import codecs
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, ID3NoHeaderError, TXXX
import csv
import json
import shutil

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = "conv_audio"


# 音声ファイルを認識結果ファイルの発話区間に従ってmp3に変換（htmlから再生する用）
def main(input_file):
    logger.info("4. 音声変換開始 - {}".format(os.path.basename(input_file)))

    # (元々の)入力の音声ファイルのパスを指定
    logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

    base = os.path.splitext(os.path.basename(input_file))[0]  # 拡張子なしのファイル名（話者）

    # 認識結果ファイルの読み込み
    recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
    logger.info("認識結果ファイル：{}".format(os.path.basename(recognize_result_file)))

    recognize_result_list = list()
    with codecs.open(recognize_result_file, "r", "CP932", "ignore") as f:
        rows = csv.reader(f)
        recognize_result_list.extend(rows)

    logger.info("音声変換中… {}".format(os.path.basename(input_file)))

    queuesize = len(recognize_result_list)

    for num, recognize_result in enumerate(recognize_result_list, start=1):
        # 話者,dstファイル名(mp3),開始時間,長さ,スコア,認識結果 の順
        try:
            audio_file = recognize_result[1]
            org_start_time = int(float(recognize_result[2]))
            length = int(float(recognize_result[3]))
            text = recognize_result[5]
        except IndexError:
            continue

        segment_signature = json.dumps(
            [org_start_time, length, text], ensure_ascii=False
        )

        if os.path.exists(audio_file):  # dstファイル(mp3)が存在する場合
            try:
                tags = ID3(audio_file)
            except ID3NoHeaderError:
                tags = ID3()
            if any(
                frame.desc == "DISNOTE_SEGMENT"
                and segment_signature in frame.text
                for frame in tags.getall("TXXX")
            ):
                logger.debug("変換後のファイルが存在しているためスキップ:{}".format(audio_file))
                continue

            logger.debug("変換後のファイルが古いので作り直す:{}".format(audio_file))

        # 入力ファイルから発話区間を切り出してmp3に変換。いったんテンポラリファイルに吐く（ffmpegの処理中にプロセスが落ちると中途半端なファイルが残ってしまうのを防ぐ）
        tmp_audio_file = common.getTemporaryFile(input_file, __file__, "mp3")
        try:
            common.runSubprocess(
                'ffmpeg -i "{}" -ss {:.3f} -t {:.3f} -vn -y "{}"'.format(
                    input_file,
                    org_start_time / 1000,
                    length / 1000,
                    tmp_audio_file,
                )
            )
        except Exception as e:
            logger.info(e)
            logger.info(
                "mp3変換に失敗したのでスキップ：{}".format(audio_file)
            )  # 変換元ファイルの内容と-ss,-tの値によっては、ffmpegが異常終了することがある（Output file is empty）
            continue

        # 分析した音声にタグをつける
        try:
            audio = EasyID3(tmp_audio_file)

            audio["artist"] = audio["albumartist"] = base
            audio["title"] = "{:0=2}:{:0=2}:{:0=2} {}".format(
                int(org_start_time / 1000 / 60 / 60),
                int(org_start_time / 1000 / 60) % 60,
                int(org_start_time / 1000) % 60,
                text,
            )
            audio.save()
        except Exception as e:
            logger.info(e)
            pass

        try:
            tags = ID3(tmp_audio_file)
        except ID3NoHeaderError:
            tags = ID3()
        tags.add(TXXX(encoding=3, desc="DISNOTE_SEGMENT", text=segment_signature))
        tags.save(tmp_audio_file)

        # テンポラリファイルからリネーム、上書き
        shutil.move(tmp_audio_file, audio_file)

        # 100行ごとか、最後の1行に進捗を出す
        if (num % 100) == 0 or (num == queuesize):
            logger.info("　音声変換中… {} {}/{}".format(base, num, queuesize))
            common.logForGui(
                logger,
                "conv_audio",
                input_file,
                progress=num,
                max=queuesize,
            )

    # 終了したことをiniファイルに保存
    common.updateConfig(input_file, {CONFIG_WORK_KEY: common.DONE})

    logger.info("音声変換終了！ {}".format(os.path.basename(input_file)))


# 直接起動した場合
if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("ファイルが指定されていません")
        sys.exit(1)

    main(sys.argv[1])
