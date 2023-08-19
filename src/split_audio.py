import os
import sys
import common
import speech_rec
import speech_rec_wit
import speech_rec_whisper
import shutil

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = "split_audio"


def main(input_file):
    # 音声ファイルをtxtファイルに出力された結果に従って分割
    logger.info("2-2. 音声分割開始 - {}".format(os.path.basename(input_file)))

    # 音声認識済みなら音声分割をスキップする
    needSplitFiles = False

    if speech_rec.reasonNotToRecognize(input_file) is None:  # 音声認識(Google) が未完了なら分割する
        logger.info("　進捗確認：音声認識(Google) 未完了")
        needSplitFiles = True

    if (
        speech_rec_wit.reasonNotToRecognize(input_file) is None
    ):  # 音声認識(wit.ai) が未完了なら分割する
        logger.info("　進捗確認：音声認識(wit.ai) 未完了")
        needSplitFiles = True

    if (
        speech_rec_whisper.reasonNotToRecognize(input_file) is None
    ):  # 音声認識(whisper) が未完了なら分割する
        logger.info("　進捗確認：音声認識(whisper) 未完了")
        needSplitFiles = True

    if not needSplitFiles:
        logger.info("音声認識済みのためスキップ(音声分割)")
        return

    # 入力の音声ファイルのパスを指定
    logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

    type = os.path.splitext(os.path.basename(input_file))[1][1:]  # 拡張子(読み込み時のフォーマット指定)

    # 分割結果ファイルの読み込み
    split_result_file = common.getSplitResultFile(input_file)
    logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))
    split_result_file_mttime = os.stat(split_result_file).st_mtime

    # 実際に音声を分割する
    base = os.path.splitext(os.path.basename(input_file))[0]  # 拡張子なしのファイル名（話者）

    with open(split_result_file, "r") as f:
        logger.info("音声分割中… {}".format(base))
        index = 0

        file_data = f.readlines()
        for line in file_data:
            # ID,分割した音声ファイル名(flac),開始時間(冒頭無音あり),終了時間(末尾無音あり),長さ(無音あり),開始時間(冒頭無音なし),長さ(末尾無音なし)の順 _split.txt
            data = line.split("\t")
            filename = data[1]
            start_time = float(data[2])
            end_time = float(data[3])

            index += 1

            if (index % 100) == 0 or (len(file_data) == index):  # 100行ごとか、最後の1行で進捗を出す
                logger.info("　音声分割中… {} {}/{}".format(base, index, len(file_data)))
                common.logForGui(logger, "split_audio", input_file, progress=index, max=len(file_data))

            if os.path.exists(filename):  # 分割した音声ファイル(flac)が存在する場合
                split_audio_file_mttime = os.stat(filename).st_mtime
                if (
                    split_audio_file_mttime > split_result_file_mttime
                ):  # 音声分割結果ファイルより後に作られた音声ファイルならOK
                    logger.debug("変換後のファイルが存在しているためスキップ:{}".format(filename))
                    continue

                logger.debug("変換後のファイルが存在しているが、古いので作り直す:{}".format(filename))

            # いったんテンポラリファイルに吐く（ffmpegの処理中にプロセスが落ちると中途半端なファイルが残ってしまうのを防ぐ）
            tmp_audio_file = common.getTemporaryFile(input_file, __file__, "flac")
            res = common.runSubprocess(
                'ffmpeg -ss {} -t {} -i "{}" -vn -acodec flac -y "{}"'.format(
                    start_time / 1000,
                    (end_time - start_time) / 1000,
                    input_file,
                    tmp_audio_file,
                )
            )

            # テンポラリファイルからリネーム、上書き
            shutil.move(tmp_audio_file, filename)

    logger.info("音声分割終了！ {}".format(os.path.basename(input_file)))


# 直接起動した場合
if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("ファイルが指定されていません")
        sys.exit(1)

    main(sys.argv[1])
