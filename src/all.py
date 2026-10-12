import sys
import os
import seg
import conv_audio
import common
import merge
import traceback
import requests
import json
import copy

logger = common.getLogger(__file__)

logger.info("----------------------------------------")
logger.info("             DisNOTE {}".format(common.getVersion()))
logger.info("----------------------------------------")


# 新しいバージョンがあったら表示する
def announceNewVersion():
    try:
        r = requests.get(
            "https://roji3.jpn.org/disnote/version.cgi", timeout=1
        )  # 公開されている最新のzipファイルのファイル名が返る(例：DisNOTE_1.2.3.zip)

        if r.status_code == 200:
            version = "v" + r.text.replace("DisNOTE_", "").replace(".zip", "")
            zipVersion = version.replace("v", "").split(".")  # ファイル名からバージョンを取得
            thisVersion = common.getVersion().replace("v", "").split(".")

            for i in range(3):  # メジャー、マイナー、パッチ の順で数字で比較
                if int(zipVersion[i]) > int(thisVersion[i]):  # 公開されているzipの方が新しい
                    print("----------------------------------------------------")
                    print("  新しいDisNOTE({}) が公開されているようです".format(version))
                    print("  https://roji3.jpn.org/disnote/")
                    print("----------------------------------------------------")
                    break
                if int(zipVersion[i]) < int(thisVersion[i]):  # 公開されているzipの方が古い（普通は無いはず）
                    break
        else:
            # logger.info("DisNOTE最新バージョンの取得に失敗：{}".format(r.status_code))
            pass

    except:
        # tb = sys.exc_info()[2]
        # logger.error(traceback.format_exc())
        pass  # 何が起きても無視


# ここからメイン処理
try:
    announceNewVersion()
    common.writeDefaultSysConfig()  # とりあえず設定ファイルを読んで未設定の値を書き込こむ
    args = common.getSysArgs()  # 引数取得

    if len(args.files) < 1:
        logger.error("ファイルが指定されていません。")
        sys.exit(1)

    # ffmpeg起動確認
    try:
        common.runSubprocess("ffmpeg -h")
        logger.info("ffmpeg 実行確認OK")
    except FileNotFoundError as e:
        logger.error(e)
        logger.error("ffmpegが見つかりません。ffmpegがDisNOTEと同じフォルダにあるか確認してください。")
        sys.exit(1)
    except Exception as e:
        logger.error(e)
        logger.error("ffmpegを実行できません。ffmpegがDisNOTEと同じフォルダにあるか確認してください。")
        sys.exit(1)

    # ffprobe起動確認
    try:
        common.runSubprocess("ffprobe -h")
        logger.info("ffprobe 実行確認OK")
    except FileNotFoundError as e:
        logger.error(e)
        logger.error("ffprobeが見つかりません。ffprobeがDisNOTEと同じフォルダにあるか確認してください。")
        sys.exit(1)
    except Exception as e:
        logger.error(e)
        logger.error("ffprobeを実行できません。ffprobeがDisNOTEと同じフォルダにあるか確認してください。")
        sys.exit(1)

    logger.info("キャンセルファイル：{}".format(common.getCancelFilePath()))



    # 入力ファイル一覧
    arg_files = copy.copy(args.files)
    arg_files.sort()  # ファイル名をソート（引数の順番だけ違う場合にファイル名を揃えるため）

    # すべてのトラックを認識するため、最初のトラックは元のファイルを、それ以降のトラックはffmpegで抜き出して認識対象に追加する
    input_files = []
    for arg_index, arg_file in enumerate(arg_files):
        logger.info(
            "---- トラック抜き出し開始：{} ({}/{}) ----".format(
                os.path.basename(arg_file), arg_index + 1, len(arg_files)
            )
        )

        # トラック情報取得
        try:
            ffprobe_result = common.getFileFormat(arg_file)
        except Exception as e:
            logger.error("処理を中断します。")
            sys.exit(1)

        streams = json.loads(ffprobe_result)

        # トラックごとに音声ファイルで出力する
        first_audio = True
        for stream_index, stream in enumerate(streams["streams"]):
            logger.info(
                "トラック {}/{} {}({})".format(
                    stream_index + 1,
                    len(streams["streams"]),
                    stream["codec_type"],
                    stream["codec_name"],
                )
            )
            if stream["codec_type"] != "audio":
                continue

            if first_audio:  # 最初のトラックは抜き出さずに、元のファイルをinput_filesに入れる
                first_audio = False
                input_files.append(arg_file)
                common.setAudioFileInfo(arg_file, arg_file, stream["index"])
                continue

            # トラックごとに音声を分解する
            basedir = os.path.dirname(arg_file)  # 入力音声ファイルの置いてあるディレクトリ
            base = common.getFileNameWithoutExtension(arg_file)  # 入力音声ファイルの置いてあるディレクトリ
            # なければmkdir
            try:
                os.mkdir(os.path.join(basedir, base))
            except FileExistsError:
                pass

            # フォーマットは変更したくなかったが、aacで出力すると変なことになることがあるのでflacに固定する
            track_filename = os.path.join(
                basedir, base, "{}_Track{}.{}".format(base, stream["index"], "flac")
            )

            if os.path.exists(track_filename) == False:
                common.runSubprocess(
                    'ffmpeg -i "{}" -map 0:{} -vn  -acodec flac "{}"'.format(
                        arg_file, stream["index"], track_filename
                    )
                )
                logger.info("トラック出力：{}".format(os.path.basename(track_filename)))

            input_files.append(track_filename)
            common.setAudioFileInfo(arg_file, track_filename, stream["index"])

        if first_audio:  # 音声トラックがないファイルだった
            logger.error("{}は音声ファイルではないようです。処理を中断します。".format(arg_file))
            sys.exit(1)

        logger.info(
            "---- トラック抜き出し終了：{} ({}/{}) ----".format(
                os.path.basename(arg_file), arg_index + 1, len(arg_files)
            )
        )

    common.logForGui(logger, "checkedAudioFiles")

    # ファイルそれぞれに対して音声認識(直列)
    try:
        for index, input_file in enumerate(input_files):
            basename = os.path.basename(input_file)
            logger.info("認識開始：{} ({}/{})".format(basename, index + 1, len(input_files)))

            # 無音解析・音声認識
            try:
                seg.main(input_file)
                common.logForGui(logger, "seg", input_file, progress=1, max=1)
            except Exception as e:
                tb = sys.exc_info()[2]
                logger.error(traceback.format_exc())
                logger.error(
                    "{} の無音解析(1)に失敗しました({})。".format(input_file, e.with_traceback(tb))
                )
                raise

            # mp3変換
            try:
                conv_audio.main(input_file)
                common.logForGui(logger, "conv_audio", input_file, progress=1, max=1)
            except Exception as e:
                tb = sys.exc_info()[2]
                logger.error(traceback.format_exc())
                logger.error(
                    "{} の音声変換(4)に失敗しました({})。".format(input_file, e.with_traceback(tb))
                )
                raise

            logger.info("認識終了：{} ({}/{})".format(basename, index + 1, len(input_files)))
            common.logForGui(logger, "prepare", input_file, progress=1, max=1)

        logger.info("全ファイル音声変換終了")

    except Exception as e:
        if common.isCancelFileExists():
            logger.error("認識がキャンセルされました（{}）".format(common.getCancelFilePath()))
            sys.exit(0)
        else:
            tb = sys.exc_info()[2]
            logger.error(traceback.format_exc())
            logger.error("処理中にエラーが発生しました({})。".format(e.with_traceback(tb)))
            sys.exit(1)

    # 結果マージ
    try:
        merge.main(input_files, arg_files)
    except Exception as e:
        if common.isCancelFileExists():
            logger.error("認識がキャンセルされました（{}）".format(common.getCancelFilePath()))
            sys.exit(0)
        else:
            tb = sys.exc_info()[2]
            logger.error(traceback.format_exc())
            logger.error("結果マージ(5)に失敗しました({})。".format(e.with_traceback(tb)))
            sys.exit(1)

finally:  # バージョン確認する
    announceNewVersion()
