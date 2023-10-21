import os
import sys
from collections import deque
import common
import traceback
import codecs
import json
import time
import whisper
import torch
import shutil


class RequestError(Exception):
    pass


logger = common.getLogger(__file__)

model = None
CONFIG_WORK_KEY = "speech_rec_whisper"
CONFIG_WORK_PROGRESS = "speech_rec_progress_whisper"
CONFIG_WORK_CONV_READY = "speech_rec_conv_ready_whisper"
CONFIG_WORK_MODEL = "speech_rec_whisper_model"

# 音声ファイルの認識を行うかどうか。行わないなら理由（ログに出力する文字列）を返す。行うならNoneを返す。
def reasonNotToRecognize(input_file):
    modelname = common.getWhisperModel()
    config = common.readConfig(input_file)

    # モデルの指定が過去の結果と異なる場合はやり直す。初回もTrueになるはず。
    model_changed = config["DEFAULT"].get(CONFIG_WORK_MODEL) != modelname

    if config["DEFAULT"].get(CONFIG_WORK_KEY) == common.DONE and (not model_changed):
        return "完了済みのためスキップ(音声認識)"

    if modelname == common.WHISPER_MODEL_NONE:
        return "Whisperを使用しない設定のためスキップ"

    return None


# 音声ファイルをtxtファイルに出力された結果に従って分割
def main(input_file):
    global model

    logger.info("3. 音声認識開始(whisper) - {}".format(os.path.basename(input_file)))
    logger.info("Cuda.available:{}".format(torch.cuda.is_available()))

    func_in_time = time.time()

    modelname = common.getWhisperModel()
    language = common.getWhisperLanguage()
    logger.info("whisperモデル：{}".format(modelname))

    config = common.readConfig(input_file)

    # モデルの指定が過去の結果と異なる場合はやり直す。初回もTrueになるはず。
    model_changed = config["DEFAULT"].get(CONFIG_WORK_MODEL) != modelname

    if config["DEFAULT"].get(CONFIG_WORK_KEY) == common.DONE and (not model_changed):
        logger.info("完了済みのためスキップ(音声認識)")
        return

    if modelname == common.WHISPER_MODEL_NONE:
        logger.info("whisperを使用しない設定のためスキップ")
        return

    if not common.isValidWhisperModel():
        raise ValueError(
            "whisperのモデル名が不正({})：DisNOTE.iniの{}の設定を確認してください".format(
                modelname, common.WHISPER_MODEL
            )
        )

    # whisperモデル読み込み（読み込みを1回にするためにglobalに保持）
    if model is None:
        # pyinstallerでバイナリを作った場合、whisperのassetsが存在しないためコピーする
        if os.path.exists("whisper/assets"):  # assetsフォルダがある場合
            assetsdir = os.path.join(os.path.dirname(whisper.__file__), "assets")
            logger.debug("assetsdir:{}".format(assetsdir))
            if os.path.exists(assetsdir):  # 通常であればここにassetsディレクトリがあるはず
                logger.debug("whisperのディレクトリにassetsディレクトリあり")
            else:
                logger.info("assetsディレクトリをコピー")
                shutil.copytree("whisper/assets", assetsdir)
        else:
            logger.debug("currentにassetsなし")

        logger.info("whisperモデル読み込み開始：{}".format(modelname))
        model = whisper.load_model(modelname)
        logger.info("whisperモデル読み込み完了：{}".format(modelname))

    if model is None:
        logger.info("whisperのモデルが指定されていないためスキップ(音声認識)")
        return

    # 中断データ
    progress = config["DEFAULT"].get(CONFIG_WORK_PROGRESS, "")

    # 中断データがあった場合は続きから、そうでない場合は最初から
    mode = "w"
    if len(progress) > 0 and (not model_changed):
        logger.info("認識途中のデータがあったため再開({})".format(progress))
        mode = "a"

    # (元々の)入力の音声ファイルのパスを指定
    logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

    base = os.path.splitext(os.path.basename(input_file))[0]  # 拡張子なしのファイル名（話者）

    # 音声認識
    num = 0

    split_result_file = common.getSplitResultFile(input_file)
    logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))

    recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
    logger.info("認識結果ファイル(whisper)：{}".format(os.path.basename(recognize_result_file)))

    split_result_queue = deque()

    with open(split_result_file, "r") as f:
        file_data = f.readlines()
        for line in file_data:
            split_result_queue.append(line.split("\t"))

    with codecs.open(recognize_result_file, mode, "CP932", "ignore") as f:
        logger.info("音声認識中(whisper)… {}".format(base))
        queuesize = len(split_result_queue)
        common.logForGui(logger, "rec", input_file, progress=0, max=queuesize,info={"engine":"whisper"})  

        # 分割して出力する音声ファイルのフォルダとプレフィックスまで指定
        audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

        while len(split_result_queue) > 0:
            split_result = split_result_queue.popleft()  # ID,ファイル名,開始時間,終了時間の順
            id = int(split_result[0])
            tmp_audio_file = split_result[1]
            start_time = int(float(split_result[2]))
            end_time = int(float(split_result[3]))
            length = int(float(split_result[4]))

            org_start_time = start_time
            org_end_time = end_time

            try:
                org_start_time = int(float(split_result[5]))
                org_end_time = int(float(split_result[6]))
            except IndexError:
                pass

            num += 1

            audio_file = "{}{}.mp3".format(audio_file_prefix, id)

            if len(progress) > 0:  # 中断データまでスキップ
                if audio_file == progress:
                    progress = ""  # 追いついたので、次の行から続き
                continue

            logger.debug("recog_start")
            result = model.transcribe(
                tmp_audio_file, language=language
            )  # , verbose=True

            text = '"' + result["text"] + '"'  # ダブルクォーテーションで囲む
            confidence = 0

            logger.debug(
                "音声認識中(whisper)… {}, {},{},{}".format(
                    base, id, int(confidence * 100), text
                )
            )
            if (id % 3) == 0 or (len(split_result_queue) == 0):  # 3行ごとか、最後の1行に進捗を出す
                logger.info("　音声認識中(whisper)… {} {}/{}".format(base, id, queuesize))
                common.logForGui(logger, "rec", input_file, progress=id, max=queuesize,info={"engine":"whisper"})  

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

            # ここまで完了した、と記録
            common.updateConfig(
                input_file,
                {
                    CONFIG_WORK_PROGRESS: audio_file,
                    CONFIG_WORK_MODEL: modelname,  # モデルを記録しておく
                },
            )

    if len(progress) > 0:  # 中断したまま終わってしまった
        common.updateConfig(input_file, {CONFIG_WORK_PROGRESS: ""})
        raise RuntimeError("音声認識再開失敗。再度実行してください。")
        return

    # 終了したことをiniファイルに保存
    common.updateConfig(
        input_file,
        {
            CONFIG_WORK_PROGRESS: "",
            CONFIG_WORK_KEY: common.DONE,
            CONFIG_WORK_MODEL: modelname,  # モデルを記録しておく  
            CONFIG_WORK_CONV_READY: "1",  # 再生用に変換してもOK
        },
    )

    func_out_time = time.time()
    logger.info(
        "音声認識終了！(whisper) {} ({:.2f}min)".format(
            os.path.basename(input_file), (func_out_time - func_in_time) / 60
        )
    )


# 直接起動した場合
if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("ファイルが指定されていません")
        sys.exit(1)

    main(sys.argv[1])
