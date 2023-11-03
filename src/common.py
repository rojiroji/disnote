import os
import sys
import logging
import logging.handlers
import configparser
import hashlib
import subprocess
import threading
import argparse
import copy
import json

VERSION = "v3.1.0"

input_file_config_lock = threading.Lock()
error_occurred = False

DONE = "done"

SYSTEM_CONF_FILE = "DisNOTE.ini"
SEG_TMP_AUDIO_LENGTH = "seg_tmp_audio_length"
SEG_FILTER_STRENGTH = "seg_filter_strength"
IS_RECOGNIZE_NOIZE = "is_recognize_noize"
WIT_AI_SERVER_ACCESS_TOKEN = "wit_ai_server_access_token"
RECOGNIZE_GOOGLE_LANGUAGE = "recognize_google_language"
REMOVE_TEMP_SPLIT_FLAC = "remove_temp_split_flac"
WHISPER_MODEL = "whisper_model"
WHISPER_LANG = "recognize_whisper_language"
WHISPER_TMP_AUDIO_LENGTH = "whisper_tmp_audio_length"
WHISPER_BINARY_DURATION = "whisper_binary_duration"
IS_USE_BINARY_WHISPER = "is_use_binary_whisper"

WHISPER_MODEL_NONE = "none"
WIT_AI_SERVER_ACCESS_TOKEN_NONE = "none"

LOG_FOR_GUI = "[PROGRESS]"  # GUI用にログを出力するときに出す文字列


# GUI用にログを出力する
def logForGui(logger, stage, input_file=None, info=None, progress=0, max=None):
    outinfo = {}

    # 何かしら特別な情報があれば追加
    if info is not None:
        outinfo.update(info)

    # 音声ファイルに対するログであればその音声ファイルの情報を追加
    if input_file is not None:
        audiofile_info = getAudioFileInfo(input_file)
        outinfo.update(audiofile_info)

    outinfo["stage"] = stage
    outinfo["progress"] = progress
    outinfo["max"] = max
    logger.info(LOG_FOR_GUI + json.dumps(outinfo))
    logger.handlers[0].flush()  # 標準出力を強制的にflush


# 認識対象の音声ファイル情報のmap（key=ファイル名 setAudioFileInfo
audiofile_infos = {}


# 音声認識対象ファイル情報登録（引数：ユーザーが渡したファイル、トラックごとに分解したファイル(=実際に音声認識するファイル)、トラック番号）
def setAudioFileInfo(orgfile, input_file, trackindex):
    track_info = {
        "orgfile": os.path.basename(orgfile),
        "input_file": os.path.basename(input_file),
        "trackindex": trackindex,
        "index": len(audiofile_infos),
    }
    audiofile_infos[input_file] = track_info
    logForGui(logger, "setAudioFileInfo", input_file)


# 音声認識対象ファイル情報取得（引数：トラックごとに分解したファイル）
def getAudioFileInfo(input_file):
    return audiofile_infos[input_file]


# 引数設定
parser = argparse.ArgumentParser()
parser.add_argument(
    "--witaitoken"
)  # wit.aiのServer Access Token（未指定の場合(None)はiniファイルの設定を使う。"none" を指定したらwit.aiを使わない）
parser.add_argument(
    "--whispermodel"
)  # Whisperのモデル（未指定の場合(None)はiniファイルの設定を使う。"none" を指定したらWhisperを使わない）
parser.add_argument("--files", nargs="*", required=True)  # ファイル
args = parser.parse_args()


# 実行引数を返す
def getSysArgs():
    return args


# DisNOTEのバージョン
def getVersion():
    return VERSION


# 共通設定iniファイルの設定値を一通り読み込み（設定値がなければ初期値が書き込まれる）
def writeDefaultSysConfig():
    getSegTmpAudioLength()
    getSegFilterStrength()
    isRecognizeNoize()
    getWitAiServerAccessToken()
    getRecognizeGoogleLanguage()
    isRemoveTempSplitFlac()
    getWhisperModel()
    getWhisperLanguage()
    getWhisperTmpAudioLength()
    getWhisperBinaryDuration()
    isUseBinaryWhisper()


# 無音解析時に作るテンポラリファイルの音声の長さ（iniファイルでは分単位だが、ミリ秒に変換して返す）
def getSegTmpAudioLength():
    min = 30  # 30分ごとに分割（デフォルト）

    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(SEG_TMP_AUDIO_LENGTH)
        min = int(val)
        if min < 10:  # 最低でも10分区切り
            min = 10

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        min = 30
        config.set("DEFAULT", SEG_TMP_AUDIO_LENGTH, str(min))
        writeSysConfig(config)

    return min * 60 * 1000


# 無音解析時にかけるノイズフィルタの強さ(0以下だとフィルタをかけない)
def getSegFilterStrength():
    ret = 0.1

    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(SEG_FILTER_STRENGTH)
        ret = float(val)

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        config.set("DEFAULT", SEG_FILTER_STRENGTH, str(ret))
        writeSysConfig(config)

    return ret


# ノイズっぽい音声を認識するかどうか
def isRecognizeNoize():
    ret = 0
    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(IS_RECOGNIZE_NOIZE)
        ret = int(val)

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        config.set("DEFAULT", IS_RECOGNIZE_NOIZE, str(ret))
        writeSysConfig(config)

    return ret != 0


# wit.aiのServer Access Token(未設定時(空文字列)はwit.aiでの認識をスキップする)
def getWitAiServerAccessToken():
    if args.witaitoken is None:  # 引数で未指定の場合はiniファイルの設定を使う
        try:
            config = readSysConfig()
            val = config["DEFAULT"].get(WIT_AI_SERVER_ACCESS_TOKEN)
            if val is not None:
                return val.strip()

        except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
            pass

        config.set("DEFAULT", WIT_AI_SERVER_ACCESS_TOKEN, "")
        writeSysConfig(config)
        return ""

    if args.witaitoken == WIT_AI_SERVER_ACCESS_TOKEN_NONE:  # 引数で"none"を指定したら使わない
        return ""

    return args.witaitoken


# GoogleAPIで認識する際の言語（デフォルトは日本語(ja-JP)）
def getRecognizeGoogleLanguage():
    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(RECOGNIZE_GOOGLE_LANGUAGE)
        if val is not None:
            val = val.strip()
            if len(val) > 0:
                return val

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        pass

    config.set("DEFAULT", RECOGNIZE_GOOGLE_LANGUAGE, "ja-JP")
    writeSysConfig(config)

    return ""


# 音声認識にかけたflacファイルを最後に削除するかどうか(デフォルトはTrue)
def isRemoveTempSplitFlac():
    ret = 1
    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(REMOVE_TEMP_SPLIT_FLAC)
        ret = int(val)

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        config.set("DEFAULT", REMOVE_TEMP_SPLIT_FLAC, str(ret))
        writeSysConfig(config)

    return ret != 0


# Whisperのモデル名
def getWhisperModel():
    if args.whispermodel is None:  # 引数で未指定の場合はiniファイルの設定を使う
        try:
            config = readSysConfig()
            val = config["DEFAULT"].get(WHISPER_MODEL)
            if val is not None:
                return val.strip()

        except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
            pass

        ret = WHISPER_MODEL_NONE
        config.set("DEFAULT", WHISPER_MODEL, ret)
        writeSysConfig(config)

        return ret

    return args.whispermodel  # 引数で直接指定


# Whisperのモデル名が有効かどうか
def isValidWhisperModel():
    return getWhisperModel() in [
        "tiny",
        "base",
        "small",
        "medium",
        "large",
        "tiny.en",
        "base.en",
        "small.en",
        "medium.en",
    ]


# Whisperの言語
def getWhisperLanguage():
    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(WHISPER_LANG)
        if val is not None:
            return val.strip()

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        pass

    ret = "ja"
    config.set("DEFAULT", WHISPER_LANG, ret)
    writeSysConfig(config)

    return ret


# Whisper(python版)解析時に作るテンポラリファイルの音声の長さ（iniファイルでは分単位だが、ミリ秒に変換して返す）
def getWhisperTmpAudioLength():
    min = 5  # 5分ごとに分割（デフォルト）

    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(WHISPER_TMP_AUDIO_LENGTH)
        min = int(val)
        if min < 1:  # 最低でも1分区切り
            min = 1

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        min = 5
        config.set("DEFAULT", WHISPER_TMP_AUDIO_LENGTH, str(min))
        writeSysConfig(config)

    return min * 60 * 1000


# Whisper(バイナリ版)解析時に読み込む音声の長さ（iniファイルでは分単位だが、ミリ秒に変換して返す）
def getWhisperBinaryDuration():
    min = 20  # 20分ごとに出力（デフォルト）

    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(WHISPER_BINARY_DURATION)
        min = int(val)
        if min < 1:  # 最低でも1分区切り
            min = 1

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        min = 20
        config.set("DEFAULT", WHISPER_BINARY_DURATION, str(min))
        writeSysConfig(config)

    return min * 60 * 1000


# バイナリ版Whisperを使うかどうか(デフォルトはTrue)
def isUseBinaryWhisper():
    ret = 1
    try:
        config = readSysConfig()
        val = config["DEFAULT"].get(IS_USE_BINARY_WHISPER)
        ret = int(val)

    except:  # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
        config.set("DEFAULT", IS_USE_BINARY_WHISPER, str(ret))
        writeSysConfig(config)

    return ret != 0


# システムconfig読み込み
def readSysConfig():
    config = configparser.ConfigParser()
    config.read(SYSTEM_CONF_FILE, "utf-8")
    return config


# システムconfig書き込み
def writeSysConfig(config):
    with open(SYSTEM_CONF_FILE, "w", encoding="utf-8") as configfile:
        config.write(configfile)


# configファイルのpath
def getConfigFile(input_file):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    ini_file = "_{}.ini".format(base)
    return os.path.join(outputdir, ini_file)


# 認識する音声ファイルのconfig読み込み
def readConfig(input_file):
    ini_file = getConfigFile(input_file)

    config = configparser.ConfigParser()
    config.read(ini_file, "utf-8")

    # 音声のhash値が違ったら最初からやり直し
    hash = inputFileHash(input_file)
    if config["DEFAULT"].get("hash") != hash:
        config = configparser.ConfigParser()
        config.set("DEFAULT", "hash", hash)

    config.set("DEFAULT", "input_file", input_file)

    return config


# 認識する音声ファイルのconfig更新
def updateConfig(input_file, difference):
    global input_file_config_lock

    with input_file_config_lock:
        config = readConfig(input_file)
        for key, val in difference.items():
            config.set("DEFAULT", key, val)

        ini_file = getConfigFile(input_file)
        with open(ini_file, "w", encoding="utf-8") as configfile:
            config.write(configfile)


# 元になる音声のhash値
def inputFileHash(input_file):
    with open(input_file, "rb") as file:
        fileData = file.read()
        hash_sha3_256 = hashlib.sha3_256(fileData).hexdigest()
        return hash_sha3_256


# 拡張子を省いたファイル名を返す（これをフォルダ名などにする）
def getFileNameWithoutExtension(input_file):
    return os.path.splitext(os.path.basename(input_file))[0]


# 分析結果ファイル
def getSegResultFile(input_file, index):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    if index > 0:
        output_file = "_{}_{}.txt".format(base, index + 1)
    else:
        output_file = "_{}.txt".format(base)

    # なければmkdir
    try:
        os.mkdir(outputdir)
    except FileExistsError:
        pass

    return os.path.join(outputdir, output_file)


# 分割音声ファイルのprefix
def getSplitAudioFilePrefix(input_file):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    output_prefix = "{}_".format(base)
    return os.path.join(outputdir, output_prefix)


# 分割結果ファイル
def getSplitResultFile(input_file):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    output_file = "_{}_split.txt".format(base)

    return os.path.join(outputdir, output_file)


# 認識結果ファイル(Google)
def getRecognizeResultFile(input_file):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    output_file = "_{}.csv".format(base)

    return os.path.join(outputdir, output_file)


# 認識結果ファイル(wit.ai)
def getRecognizeResultFileWitAI(input_file):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    output_file = "_{}_witai.csv".format(base)

    return os.path.join(outputdir, output_file)


# 認識結果ファイル(whisper) モデルごとにファイルを分ける
def getRecognizeResultFileWhisper(input_file):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    output_file = "_{}_whisper_{}.csv".format(base, getWhisperModel())

    return os.path.join(outputdir, output_file)


# 認識中間ファイル(whisper)
def getSegmentFileWhisper(input_file):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    output_file = "_{}_whisper_segment.csv".format(base)

    return os.path.join(outputdir, output_file)


# テンポラリファイル
def getTemporaryFile(input_file, srcfile, extension):
    base = getFileNameWithoutExtension(input_file)
    basedir = os.path.dirname(input_file)  # 入力音声ファイルの置いてあるディレクトリ
    outputdir = os.path.join(basedir, base)  # 各種ファイルの出力先ディレクトリ

    prefix = os.path.splitext(os.path.basename(srcfile))[0]  # ソースファイル名（拡張子を取る）
    output_file = "_{}.{}".format(prefix, extension)

    return os.path.join(outputdir, output_file)


# logger
def getLogger(srcfile):
    name = os.path.splitext(os.path.basename(srcfile))[0]  # ソースファイル名（拡張子を取る）

    logger = logging.getLogger(name)  # logger名loggerを取得
    logger.setLevel(logging.INFO)

    # logフォルダがなければmkdir
    try:
        os.mkdir("log")
    except FileExistsError:
        pass

    # 標準出力
    handler1 = logging.StreamHandler(sys.stdout)
    handler1.setLevel(logging.INFO)
    handler1.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s"))

    # ログファイル
    handler2 = logging.handlers.RotatingFileHandler(
        filename="log/speechrec.log", maxBytes=1024 * 1024 * 10, backupCount=3
    )
    handler2.setLevel(logging.INFO)
    handler2.setFormatter(
        logging.Formatter(
            "%(asctime)s %(process)8d [%(levelname)s] %(name)s %(message)s"
        )
    )

    # loggerに2つのハンドラを設定
    logger.addHandler(handler1)  # 0番目は標準出力であること（logForGuiでflushするため）
    logger.addHandler(handler2)

    return logger


# common.pyのlogger
logger = getLogger(__file__)


# サブプロセス実行（returncodeが非0の場合は標準エラー出力をログに吐いて例外を投げる。正常終了時、res.stdoutに標準出力）
def runSubprocess(args):
    res = subprocess.run(
        args, encoding="utf-8", capture_output=True, text=True
    )  # , stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        logger.error(args)
        logger.error(res.stderr)

        if res.stderr is None:
            logger.error(res.stdout)
            raise RuntimeError(res.stdout)

        raise RuntimeError(res.stderr)

    return res


# メディアファイルのフォーマットを返す
def getFileFormat(input_file):
    try:
        res = runSubprocess(
            'ffprobe.exe -v error -show_streams -print_format json "{}"'.format(
                input_file
            )
        )
        return res.stdout
    except Exception as e:
        logger = getLogger(__file__)
        logger.error("フォーマット確認失敗。{} は音声ファイルではないようです。".format(input_file))
        pass


# スレッド処理中に例外が発生したフラグを立てる。このフラグが立っていたら、各スレッドは可及的速やかにスレッドを中断する
def errorOccurred():
    global error_occurred
    error_occurred = True


# スレッド処理中に例外が発生したかどうか
def isErrorOccurred():
    global error_occurred
    return error_occurred
