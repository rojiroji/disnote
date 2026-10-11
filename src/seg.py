import os
import sys
import csv
import codecs
import common
import time
import torch
from faster_whisper import WhisperModel

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = "seg_whisper_" + common.getWhisperModel()  # モデルごとに完了状態を記録
CONFIG_WORK_PROGRESS = "seg_progress_whisper_" + common.getWhisperModel()
CONFIG_SEG_SPLIT = "seg_split"
CONFIG_WORK_REC_KEY = "speech_rec_whisper_" + common.getWhisperModel()  # モデルごとに認識結果出力の完了状態を記録
CONFIG_WORK_CONV_READY = "speech_rec_conv_ready_whisper"

model = None


def main(input_file):
    global model

    logger.info("1. 無音解析開始(faster-whisper) - {}".format(os.path.basename(input_file)))
    logger.info("Cuda.available:{}".format(torch.cuda.is_available()))
    func_in_time = time.time()

    config = common.readConfig(input_file)
    if config["DEFAULT"].get(CONFIG_WORK_KEY) == common.DONE:
        logger.info("完了済みのためスキップ(無音解析)")
        return

    modelname = common.getWhisperModel()
    language = common.getWhisperLanguage()
    logger.info("faster-whisperモデル：{}".format(modelname))

    if not common.isValidWhisperModel():
        raise ValueError(
            "whisperのモデル名が不正({})：DisNOTE.iniの{}の設定を確認してください".format(
                modelname, common.WHISPER_MODEL
            )
        )

    progress = config["DEFAULT"].getint(CONFIG_WORK_PROGRESS, 0)

    if progress > 0:
        prev_split_len = config["DEFAULT"].getint(CONFIG_SEG_SPLIT)  # ミリ秒で管理する
        if prev_split_len != common.getSegTmpAudioLength():
            logger.info(
                "無音解析途中のデータがあったが、分割単位が異なるため最初({},{},{})".format(
                    progress, prev_split_len, common.getSegTmpAudioLength()
                )
            )
            progress = 0  # 区切り単位が異なっていたら最初からやりなおし
        else:
            logger.info("無音解析途中のデータがあったため再開({})".format(progress))

    # faster-whisperモデル読み込み（読み込みを1回にするためにglobalに保持）
    if model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        logger.info("faster-whisperモデル読み込み開始：{}({})".format(modelname, device))
        model = WhisperModel(modelname, device=device, compute_type=compute_type)
        logger.info("faster-whisperモデル読み込み完了：{}".format(modelname))

    # 音声ファイルを無音で分割して秒数とかを出力

    # 入力の音声ファイルのパスを引数で指定
    logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

    # 音声の長さを取得(ffprobe実行)
    logger.info("音声ファイル読み込み中…")
    res = common.runSubprocess(
        'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{}"'.format(
            input_file
        )
    )
    duration = float(res.stdout.strip()) * 1000  # 再生時間(ミリ秒)
    logger.info("無音解析処理中… (duration:{}sec)".format(int(duration / 1000)))

    # 一定時間ごとに分割
    index = progress
    split_len = common.getSegTmpAudioLength()
    start_time = split_len * index
    tmp_audio_file = "log/tmp.flac"  # 一時ファイル（面倒なので消さない）

    logger.info("分割単位：{}min".format(int(split_len / 60 / 1000)))

    base = os.path.splitext(os.path.basename(input_file))[0]  # 拡張子なしのファイル名（話者）

    # 発話区間キャッシュ(開始・終了時刻(絶対時刻,ミリ秒)と認識テキスト)
    segment_cache_file = common.getSegmentFileWhisper(input_file)
    logger.info("発話区間キャッシュファイル：{}".format(os.path.basename(segment_cache_file)))
    cache_mode = "a" if progress > 0 else "w"

    # 認識結果ファイル(whisper)。発話区間から直接出力する
    recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
    logger.info("認識結果ファイル(whisper)：{}".format(os.path.basename(recognize_result_file)))
    audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

    # 途中再開の場合は、キャッシュファイルに残っている過去の区間を読み込んでおく(認識結果のID連番継続のため)
    all_segments = []
    if progress > 0:
        with codecs.open(segment_cache_file, "r", "CP932", "ignore") as f:
            for row in csv.reader(f):
                if len(row) < 3:
                    continue
                all_segments.append((int(row[0]), int(row[1]), row[2]))

    with codecs.open(segment_cache_file, cache_mode, "CP932", "ignore") as cache_f, codecs.open(
        recognize_result_file, cache_mode, "CP932", "ignore"
    ) as rec_f:
        cache_writer = csv.writer(cache_f)

        while start_time < duration:
            logger.info(
                "　無音解析処理中… {} {}/{}".format(base, index + 1, int(duration / split_len) + 1)
            )
            common.logForGui(
                logger,
                "seg",
                input_file,
                progress=index,
                max=int(duration / split_len),
            )

            end_time = min(start_time + split_len, duration)

            # ffmpegで分割
            filter_start_time = time.time()
            common.runSubprocess(
                'ffmpeg -ss {} -t {} -i "{}" -vn -acodec flac -y {}'.format(
                    start_time / 1000,
                    (end_time - start_time) / 1000,
                    input_file,
                    tmp_audio_file,
                )
            )
            filter_end_time = time.time()
            logger.debug(
                "　フィルタ処理 {:.2f}min".format((filter_end_time - filter_start_time) / 60)
            )

            # 区間検出+音声認識を同時に実行(VADフィルターで無音部分を除いた区間の時刻が得られる)
            seg_start_time = time.time()
            segments, info = model.transcribe(
                tmp_audio_file,
                language=language,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
            )
            segments = list(segments)  # ジェネレータを消費して確定させる
            seg_end_time = time.time()
            logger.debug(
                "　無音解析・音声認識処理 {:.2f}min".format((seg_end_time - seg_start_time) / 60)
            )

            # 発話区間の開始・終了時刻(絶対時刻,ミリ秒)と認識テキストを保存
            for seg_item in segments:
                abs_start_ms = int(start_time + seg_item.start * 1000)
                abs_end_ms = int(start_time + seg_item.end * 1000)
                text = seg_item.text.strip().replace("\n", " ")
                cache_writer.writerow([abs_start_ms, abs_end_ms, text])
                all_segments.append((abs_start_ms, abs_end_ms, text))

                # 認識結果ファイルに出力(話者,ファイル名(mp3),開始時間,長さ,スコア,認識結果)
                audio_file = "{}{}.mp3".format(audio_file_prefix, len(all_segments))
                rec_f.write(
                    '{},{},{},{},{},"{}"\n'.format(
                        base,
                        audio_file,
                        abs_start_ms,
                        abs_end_ms - abs_start_ms,
                        0,
                        text,
                    )
                )
            cache_f.flush()
            rec_f.flush()

            start_time += split_len
            index = index + 1

            # ここまで完了した、と記録
            common.updateConfig(
                input_file,
                {CONFIG_WORK_PROGRESS: str(index), CONFIG_SEG_SPLIT: str(split_len)},
            )

            if common.isErrorOccurred():  # 他のスレッドでエラーが起きていたら強制終了する
                return

    # 終了したことをiniファイルに保存
    common.updateConfig(
        input_file,
        {
            CONFIG_WORK_KEY: common.DONE,
            CONFIG_WORK_PROGRESS: "",
            CONFIG_SEG_SPLIT: str(split_len),
            CONFIG_WORK_REC_KEY: common.DONE,
            CONFIG_WORK_CONV_READY: "1",  # 再生用に変換してもOK
        },
    )
    common.logForGui(logger, "rec", input_file, progress=1, max=1, info={"engine": "whisper"})

    func_out_time = time.time()
    logger.info(
        "無音解析終了！ {} ({:.2f}min)".format(
            os.path.basename(input_file), (func_out_time - func_in_time) / 60
        )
    )


# 直接起動した場合
if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("ファイルが指定されていません")
        sys.exit(1)

    main(sys.argv[1])
