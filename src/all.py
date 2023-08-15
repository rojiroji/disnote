import sys
import os
import seg
import split
import split_audio
import speech_rec
import speech_rec_wit
import speech_rec_whisper
import conv_audio
import common
import merge
import traceback
import requests
import json
import copy
import time
import thread
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.error import HTTPError
import socket

logger = common.getLogger(__file__)

logger.info("----------------------------------------")
logger.info("             DisNOTE {}".format(common.getVersion()))
logger.info("----------------------------------------")


# 認識準備を行うスレッド
def prepare(input_files):
    global logger
    try:
        for index, input_file in enumerate(input_files):
            if common.isErrorOccurred():  # 他のスレッドでエラーが起きていたら強制終了する
                return

            basename = os.path.basename(input_file)

            logger.info(
                "認識準備開始：{} ({}/{})".format(basename, index + 1, len(input_files))
            )

            # フォーマット確認
            try:
                common.getFileFormat(input_file)
            except Exception as e:
                logger.error("処理を中断します。")
                raise

            # 無音解析
            try:
                seg.main(input_file)
            except Exception as e:
                tb = sys.exc_info()[2]
                logger.error(traceback.format_exc())
                logger.error(
                    "{} の無音解析(1)に失敗しました({})。".format(input_file, e.with_traceback(tb))
                )
                raise

            # 音声分割設定
            try:
                split.main(input_file)
            except Exception as e:
                tb = sys.exc_info()[2]
                logger.error(traceback.format_exc())
                logger.error(
                    "{} の音声分割設定(2-1)に失敗しました({})。".format(
                        input_file, e.with_traceback(tb)
                    )
                )
                raise

            # 音声分割
            try:
                split_audio.main(input_file)
            except Exception as e:
                tb = sys.exc_info()[2]
                logger.error(traceback.format_exc())
                logger.error(
                    "{} の音声分割(2-2)に失敗しました({})。".format(input_file, e.with_traceback(tb))
                )
                raise

            # 音声認識スレッドに登録
            thread.pushReadyRecognizeList(input_file)

            logger.info(
                "認識準備終了：{} ({}/{})".format(basename, index + 1, len(input_files))
            )
    except Exception as e:
        common.errorOccurred()
        raise


# Whisper（バイナリ版）の辞書をダウンロードするスレッド
def downloadWhisperGgmlModel():
    try:
        speech_rec_whisper.downloadWhisperGgmlModel()
    except Exception as e:
        common.errorOccurred()
        tb = sys.exc_info()[2]
        logger.error(traceback.format_exc())
        logger.error("Whisper（バイナリ版）辞書のダウンロードに失敗しました({})。".format(e.with_traceback(tb)))
        raise


# 音声認識を行うスレッド(Google音声認識)
def speechRecognizeGoogle(prepareThread):
    global logger

    try:
        while True:
            if common.isErrorOccurred():  # 他のスレッドでエラーが起きていたら強制終了する
                return

            time.sleep(1)
            logger.debug("スレッド待機中(speechRecognizeGoogle)")

            input_file = thread.popReadyRecognizeListGoogle()
            if input_file is None:
                if (
                    prepareThread.done()
                ):  # 仕事リストが空＆prepareThreadが終了していたら、もうリストに追加されることはないので終了する
                    logger.info("全ファイル音声認識終了(Google)")
                    return
                continue

            # 音声認識
            speech_rec.main(input_file)
            thread.pushReadyConvertListGoogle(input_file)
    except Exception as e:
        common.errorOccurred()
        tb = sys.exc_info()[2]
        logger.error(traceback.format_exc())
        logger.error("{} の音声認識(3)に失敗しました({})。".format(input_file, e.with_traceback(tb)))
        raise


# 音声認識を行うスレッド(wit.ai音声認識)
def speechRecognizeWitAI(prepareThread):
    global logger

    try:
        while True:
            if common.isErrorOccurred():  # 他のスレッドでエラーが起きていたら強制終了する
                return

            time.sleep(1)
            logger.debug("スレッド待機中(speechRecognizeWitAI)")

            input_file = thread.popReadyRecognizeListWitAI()
            if input_file is None:
                if (
                    prepareThread.done()
                ):  # 仕事リストが空＆prepareThreadが終了していたら、もうリストに追加されることはないので終了する
                    logger.info("全ファイル音声認識終了(wit.ai)")
                    return
                continue

            # 音声認識
            retry_count = 0
            while True:  # 何度かリトライ
                retry = False
                try:
                    speech_rec_wit.main(input_file)
                except HTTPError as e:  # タイムアウトエラーの場合はリトライする
                    if e.code == 408:
                        retry = True
                    else:
                        raise e
                except socket.timeout:  # タイムアウトエラーの場合はリトライする
                    retry = True
                except Exception as e:
                    raise e

                if retry:
                    retry_count += 1

                    if retry_count <= 3:  # 最大3回
                        logger.info(
                            "wit.aiの音声認識でタイムアウトが発生したためリトライします({})".format(retry_count)
                        )
                        time.sleep(5)
                    else:
                        raise RuntimeError("リトライ回数が上限を超えました({})。".format(retry_count))
                else:
                    # 完了
                    thread.pushReadyConvertListWitAI(input_file)
                    break

    except Exception as e:
        common.errorOccurred()
        tb = sys.exc_info()[2]
        logger.error(traceback.format_exc())
        logger.error("{} の音声認識(3)に失敗しました({})。".format(input_file, e.with_traceback(tb)))
        raise


# 音声認識を行うスレッド(whisper音声認識)
def speechRecognizeWhisper(prepareThread, downloadWhisperGgmlModelThread):
    global logger

    try:
        while True:
            if common.isErrorOccurred():  # 他のスレッドでエラーが起きていたら強制終了する
                return

            time.sleep(1)
            logger.debug("スレッド待機中(speechRecognizeWhisper)")

            # 無音検出とWhisperは両方クライアントのリソースを使うので、並列では行わない
            if not prepareThread.done():
                continue

            # 辞書ダウンロードが終わっていなかったら待つ
            if not downloadWhisperGgmlModelThread.done():
                logger.debug("辞書ダウンロード待ち")
                continue

            input_file = thread.popReadyRecognizeListWhisper()
            if input_file is None:
                if (
                    prepareThread.done()
                ):  # 仕事リストが空＆prepareThreadが終了していたら、もうリストに追加されることはないので終了する
                    logger.info("全ファイル音声認識終了(Whisper)")
                    return
                continue

            # 音声認識
            speech_rec_whisper.main(input_file)
            thread.pushReadyConvertListWhisper(input_file)
    except Exception as e:
        common.errorOccurred()
        tb = sys.exc_info()[2]
        logger.error(traceback.format_exc())
        logger.error("{} の音声認識(3)に失敗しました({})。".format(input_file, e.with_traceback(tb)))
        raise


# mp3への変換を行うスレッド
def convert(recognizeThreads):
    global logger
    try:
        while True:
            if common.isErrorOccurred():  # 他のスレッドでエラーが起きていたら強制終了する
                return

            time.sleep(1)

            recognize_done = True
            for t in recognizeThreads:
                recognize_done &= t.done()  # 音声認識スレッドがすべて終了しているかどうか

            logger.debug("スレッド待機中(convert) 音声認識全て終了：{}".format(recognize_done))

            input_file = thread.popReadyConvertList(
                pop_and=(not recognize_done)
            )  # 音声認識スレッドが終了していなかったらandを取る。終了していたらorで妥協する（何らかの原因でandが空だった場合に永遠に終了しないため）。
            if input_file is None:
                if recognize_done:  # 音声認識が終了していたら、もうリストに追加されることはないので終了する
                    return
                continue

            # 音声変換
            conv_audio.main(input_file)

    except Exception as e:
        common.errorOccurred()
        tb = sys.exc_info()[2]
        logger.error(traceback.format_exc())
        logger.error("{} の音声変換(4)に失敗しました({})。".format(input_file, e.with_traceback(tb)))
        raise


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

    # Whisper(バイナリ版)起動確認
    if common.isUseBinaryWhisper() and common.isValidWhisperModel():
        process = os.path.join("whisper", "disnote_whisper.exe")
        try:
            logger.info("{} 実行確認".format(process))
            res = common.runSubprocess("{} -h".format(process))
            logger.info("{} 実行確認OK".format(process))
        except FileNotFoundError as e:
            logger.error(e)
            logger.error("{}が見つかりません。{}があるか確認してください。".format(process))
            sys.exit(1)
        except Exception as e:
            logger.error(e)
            logger.error("{}が実行できません。{}の状態を確認してください。".format(process))
            sys.exit(1)

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
                common.addAudioFile(arg_file, arg_file, stream["index"])
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
            common.addAudioFile(arg_file, track_filename, stream["index"])

        if first_audio:  # 音声トラックがないファイルだった
            logger.error("{}は音声ファイルではないようです。処理を中断します。".format(arg_file))
            sys.exit(1)

        logger.info(
            "---- トラック抜き出し終了：{} ({}/{}) ----".format(
                os.path.basename(arg_file), arg_index + 1, len(arg_files)
            )
        )

    # ファイルそれぞれに対して音声認識
    with ThreadPoolExecutor() as executor:
        threadList = list()

        try:
            prepareThread = executor.submit(prepare, input_files)  # 認識準備スレッド
            threadList.append(prepareThread)

            downloadWhisperGgmlModelThread = executor.submit(
                downloadWhisperGgmlModel
            )  # Whisper（バイナリ版）の辞書をダウンロードするスレッド
            threadList.append(downloadWhisperGgmlModelThread)

            recognizeThreads = list()
            recognizeThreads.append(
                executor.submit(speechRecognizeGoogle, prepareThread)
            )  # 音声認識スレッド(Google)
            recognizeThreads.append(
                executor.submit(speechRecognizeWitAI, prepareThread)
            )  # 音声認識スレッド(wit.ai)
            recognizeThreads.append(
                executor.submit(
                    speechRecognizeWhisper,
                    prepareThread,
                    downloadWhisperGgmlModelThread,
                )
            )  # 音声認識スレッド(Whisper)
            threadList.extend(recognizeThreads)

            e = prepareThread.exception()  # 認識準備スレッド終了待ち
            if e is not None:
                raise e
            logger.info("全ファイル認識準備終了")

            convertThread = executor.submit(convert, recognizeThreads)  # mp3変換スレッド
            threadList.append(convertThread)

            for t in recognizeThreads:  # 音声認識スレッド終了待ち
                e = t.exception()
                if e is not None:
                    raise e

            e = convertThread.exception()  # mp3変換スレッド終了待ち
            if e is not None:
                raise e
            logger.info("全ファイル音声変換終了")

        except Exception as e:  # 例外が起きたら、すべてのスレッドの終了を待ってからログを出力して終了する
            common.errorOccurred()
            logger.error("スレッド処理中にエラーが発生したため全スレッドを停止")
            for t in threadList:
                try:
                    t.result()
                except Exception as e:
                    pass

            tb = sys.exc_info()[2]
            logger.error(traceback.format_exc())
            logger.error("スレッド処理中にエラーが発生しました({})。".format(e.with_traceback(tb)))
            sys.exit(1)

    # 結果マージ
    try:
        merge.main(input_files, arg_files)
    except Exception as e:
        tb = sys.exc_info()[2]
        logger.error(traceback.format_exc())
        logger.error("結果マージ(5)に失敗しました({})。".format(e.with_traceback(tb)))
        sys.exit(1)

finally:  # バージョン確認する
    announceNewVersion()
