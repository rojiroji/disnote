import os
import sys
import logging
import logging.handlers
import configparser
import hashlib
import subprocess

DONE = "done"
SYSTEM_CONF_FILE="DisNOTE.ini"
SEG_TMP_AUDIO_LENGTH="seg_tmp_audio_length"
IS_RECOGNIZE_NOIZE="is_recognize_noize"

def getVersion():
	return "v1.3.0"

# 無音検出時に作るテンポラリファイルの音声の長さ（ミリ秒）
def getSegTmpAudioLength():
	min = 30 # 30分ごとに分割（デフォルト）

	try:
		config = readSysConfig()
		val = config['DEFAULT'].get(SEG_TMP_AUDIO_LENGTH)
		min = int(val)
		if min < 10: # 最低でも10分区切り
			min = 10
			
	except: # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
		min = 30
		config.set('DEFAULT',SEG_TMP_AUDIO_LENGTH , str(min))
		writeSysConfig(config)
	
	return min * 60 * 1000

# ノイズっぽい音声を認識するかどうか
def isRecognizeNoize():
	ret = 0;
	try:
		config = readSysConfig()
		val = config['DEFAULT'].get(IS_RECOGNIZE_NOIZE)
		ret = int(val)

	except: # 設定ファイルが読めなかったり(初回起動時)、値がおかしかったらデフォルトで保存
		config.set('DEFAULT',IS_RECOGNIZE_NOIZE , str(ret))
		writeSysConfig(config)
	
	return ret != 0;


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
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	ini_file = "_{}.ini".format(base)
	return os.path.join(outputdir, ini_file)

# config読み込み
def readConfig(input_file):
	ini_file = getConfigFile(input_file)

	config = configparser.ConfigParser()
	config.read(ini_file, "utf-8")
	
	# 音声のhash値が違ったら最初からやり直し
	hash = inputFileHash(input_file)
	if config['DEFAULT'].get('hash') != hash:
		config = configparser.ConfigParser()
		config.set('DEFAULT', 'hash', hash)

	config.set('DEFAULT', 'input_file', input_file)
	
	return config

# config書き込み
def writeConfig(input_file, config):
	ini_file = getConfigFile(input_file)
	with open(ini_file, "w", encoding="utf-8") as configfile:
		config.write(configfile)

# 元になる音声のhash値
def inputFileHash(input_file):
	with open(input_file, 'rb') as file:
		fileData = file.read()
		hash_sha3_256 = hashlib.sha3_256(fileData).hexdigest()
		return hash_sha3_256

# 拡張子を省いたファイル名を返す（これをフォルダ名などにする）
def getFileNameWithoutExtension(input_file):
	return os.path.splitext(os.path.basename(input_file))[0]

# 分析結果ファイル
def getSegResultFile(input_file, index):
	base = getFileNameWithoutExtension(input_file)
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	if index > 0:
		output_file = "_{}_{}.txt".format(base, index+1)
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
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	output_prefix = "{}_".format(base)
	return os.path.join(outputdir, output_prefix)

# 分割結果ファイル
def getSplitResultFile(input_file):
	base = getFileNameWithoutExtension(input_file)
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	output_file = "_{}_split.txt".format(base)

	return os.path.join(outputdir, output_file)

# 認識結果ファイル
def getRecognizeResultFile(input_file):
	base = getFileNameWithoutExtension(input_file)
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	output_file = "_{}.csv".format(base)

	return os.path.join(outputdir, output_file)

# logger
def getLogger(srcfile):
	name = os.path.splitext(os.path.basename(srcfile))[0] # ソースファイル名（拡張子を取る）
	
	logger = logging.getLogger(name)    #logger名loggerを取得
	logger.setLevel(logging.INFO)

	# logフォルダがなければmkdir
	try:
		os.mkdir("log")
	except FileExistsError:
		pass

	#標準出力
	handler1 = logging.StreamHandler(sys.stdout)
	handler1.setLevel(logging.INFO)
	handler1.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

	#ログファイル
	handler2 = logging.handlers.RotatingFileHandler(filename="log/speechrec.log", maxBytes=1024 * 1024 * 10, backupCount=3)
	handler2.setLevel(logging.INFO)
	handler2.setFormatter(logging.Formatter("%(asctime)s %(process)8d [%(levelname)s] %(name)s %(message)s"))

	#loggerに2つのハンドラを設定
	logger.addHandler(handler1)
	logger.addHandler(handler2)
	
	return logger


# サブプロセス実行（returncodeが非0の場合は標準エラー出力をログに吐いて例外を投げる。正常終了時、res.stdoutに標準出力）
def runSubprocess(args):
	res = subprocess.run(args, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if res.returncode != 0:
		logger = getLogger(__file__)
		logger.error(res.stderr)
		raise RuntimeError(res.stderr)

	return res

# メディアファイルのフォーマットを返す
def getFileFormat(input_file):
	try:
		res = runSubprocess("ffprobe.exe -v error -show_streams -print_format json \"{}\"".format(input_file))
		return res.stdout
	except Exception as e:
		logger = getLogger(__file__)
		logger.error("フォーマット確認失敗。{} は音声ファイルではないようです。".format(input_file))
		pass
