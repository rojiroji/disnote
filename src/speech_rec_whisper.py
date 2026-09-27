import os
import sys
import common
import traceback
import codecs
import csv
import time


class RequestError(Exception):
    pass


logger = common.getLogger(__file__)

CONFIG_WORK_KEY = "speech_rec_whisper_" + common.getWhisperModel()  # モデルごとに進捗を記録
CONFIG_WORK_CONV_READY = "speech_rec_conv_ready_whisper"


# 音声ファイルの認識を行うかどうか。行わないなら理由（ログに出力する文字列）を返す。行うならNoneを返す。
def reasonNotToRecognize(input_file):
    config = common.readConfig(input_file)

    if config["DEFAULT"].get(CONFIG_WORK_KEY) == common.DONE:
        return "完了済みのためスキップ(音声認識)"

    return None


# seg.py(faster-whisper)が検出した発話区間キャッシュから、分割結果ファイルの区間に対応する認識結果を出力する
def main(input_file):
    logger.info("3. 音声認識結果出力開始(whisper) - {}".format(os.path.basename(input_file)))

    func_in_time = time.time()

    config = common.readConfig(input_file)
    if config["DEFAULT"].get(CONFIG_WORK_KEY) == common.DONE:
        logger.info("完了済みのためスキップ(音声認識)")
        return

    # (元々の)入力の音声ファイルのパスを指定
    logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

    base = os.path.splitext(os.path.basename(input_file))[0]  # 拡張子なしのファイル名（話者）

    split_result_file = common.getSplitResultFile(input_file)
    logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))

    segment_cache_file = common.getSegmentFileWhisper(input_file)
    logger.info("発話区間キャッシュファイル：{}".format(os.path.basename(segment_cache_file)))

    recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
    logger.info("認識結果ファイル(whisper)：{}".format(os.path.basename(recognize_result_file)))

    # seg.pyが書き出した発話区間キャッシュ(開始・終了時刻(絶対時刻,ミリ秒),認識テキスト)を読み込み
    segments = []
    with codecs.open(segment_cache_file, "r", "CP932", "ignore") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            segments.append((int(row[0]), int(row[1]), row[2]))

    audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

    with codecs.open(split_result_file, "r", "CP932", "ignore") as f:
        file_data = f.readlines()

    queuesize = len(file_data)

    with codecs.open(recognize_result_file, "w", "CP932", "ignore") as f:
        logger.info("音声認識結果出力中(whisper)… {}".format(base))
        common.logForGui(
            logger, "rec", input_file, progress=0, max=queuesize, info={"engine": "whisper"},
        )

        for num, line in enumerate(file_data, start=1):
            # ID,分割した音声ファイル名(flac),開始時間(冒頭無音あり),終了時間(末尾無音あり),長さ(無音あり),開始時間(冒頭無音なし),長さ(末尾無音なし)の順
            split_result = line.split("\t")
            id = int(split_result[0])

            org_start_time = int(float(split_result[2]))
            org_end_time = int(float(split_result[3]))
            try:
                org_start_time = int(float(split_result[5]))
                org_end_time = int(float(split_result[6]))
            except IndexError:
                pass

            audio_file = "{}{}.mp3".format(audio_file_prefix, id)

            # 分割区間と時間的に重なっている発話区間のテキストをつなげる
            texts = [
                seg_text
                for seg_start, seg_end, seg_text in segments
                if seg_start < org_end_time and seg_end > org_start_time
            ]
            text = '"' + " ".join(texts) + '"'  # ダブルクォーテーションで囲む
            confidence = 0

            if (num % 100) == 0 or (num == queuesize):  # 100件ごとか、最後の1件で進捗を出す
                logger.info("　音声認識結果出力中(whisper)… {} {}/{}".format(base, num, queuesize))
                common.logForGui(
                    logger, "rec", input_file, progress=num, max=queuesize, info={"engine": "whisper"},
                )

            f.write(
                "{},{},{},{},{},{}\n".format(
                    base,
                    audio_file,
                    org_start_time,
                    org_end_time - org_start_time,
                    int(confidence * 100),
                    text,
                )
            )
            f.flush()

            if common.isErrorOccurred():  # 他のスレッドでエラーが起きていたら強制終了する
                return

    # 終了したことをiniファイルに保存
    common.updateConfig(
        input_file,
        {
            CONFIG_WORK_KEY: common.DONE,
            CONFIG_WORK_CONV_READY: "1",  # 再生用に変換してもOK
        },
    )

    func_out_time = time.time()
    logger.info(
        "音声認識結果出力終了！(whisper) {} ({:.2f}min)".format(
            os.path.basename(input_file), (func_out_time - func_in_time) / 60
        )
    )


# 直接起動した場合
if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("ファイルが指定されていません")
        sys.exit(1)

    main(sys.argv[1])

