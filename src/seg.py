import os
import sys
from inaSpeechSegmenter import Segmenter
from inaSpeechSegmenter.export_funcs import seg2csv, seg2textgrid
import common
import time
import torch

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = "seg"
CONFIG_WORK_PROGRESS = "seg_progress"
CONFIG_SEG_SPLIT = "seg_split"


def main(input_file):
    logger.info("1. 無音解析開始 - {}".format(os.path.basename(input_file)))
    logger.info("Cuda.available:{}".format(torch.cuda.is_available()))
    func_in_time = time.time()

    config = common.readConfig(input_file)
    if config["DEFAULT"].get(CONFIG_WORK_KEY) == common.DONE:
        logger.info("完了済みのためスキップ(無音解析)")
        return

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

    # ノイズフィルタの設定
    filter = ""
    if common.getSegFilterStrength() > 0:  # anlmdnフィルタをかける
        filter = "-af anlmdn=s={}".format(common.getSegFilterStrength())

    logger.info("ノイズフィルタ：{}".format("なし" if len(filter) == 0 else filter))

    while start_time < duration:
        # 分析結果ファイル
        seg_result_file = common.getSegResultFile(input_file, index)
        logger.info("分析結果ファイル：{}".format(os.path.basename(seg_result_file)))
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
        res = common.runSubprocess(
            'ffmpeg -ss {} -t {} -i "{}" {} -vn -acodec flac -y {}'.format(
                start_time / 1000,
                (end_time - start_time) / 1000,
                input_file,
                filter,
                tmp_audio_file,
            )
        )
        filter_end_time = time.time()
        logger.debug(
            "　フィルタ処理 {:.2f}min".format((filter_end_time - filter_start_time) / 60)
        )

        # 区間検出実行
        seg_start_time = time.time()
        seg = Segmenter(vad_engine="smn", detect_gender=False)
        segmentation = seg(tmp_audio_file)
        seg_end_time = time.time()

        # csv(という名のタブ)出力
        seg2csv(segmentation, seg_result_file)
        seg2sv_end_time = time.time()

        logger.debug(
            "　無音解析処理 {:.2f}min+{:.2f}min".format(
                (seg_end_time - seg_start_time) / 60,
                (seg2sv_end_time - seg_end_time) / 60,
            )
        )

        start_time += split_len
        index = index + 1

        # ここまで完了した、と記録
        common.updateConfig(
            input_file,
            {CONFIG_WORK_PROGRESS: str(index), CONFIG_SEG_SPLIT: str(split_len)},
        )

    # 終了したことをiniファイルに保存
    common.updateConfig(
        input_file,
        {
            CONFIG_WORK_KEY: common.DONE,
            CONFIG_WORK_PROGRESS: "",
            CONFIG_SEG_SPLIT: str(split_len),
        },
    )

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
