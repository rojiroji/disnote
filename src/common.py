import os
import sys
import logging
import logging.handlers
import configparser
import hashlib

DONE = "done"

def getVersion():
	return "v1.0.1"

# configファイルのpath
def getConfigFile(input_file):
	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（これをフォルダ名などにする）
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

# 分析結果ファイル
def getSegResultFile(input_file):
	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（これをフォルダ名などにする）
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	output_file = "_{}.txt".format(base)
		
	# なければmkdir
	try:
		os.mkdir(outputdir)
	except FileExistsError:
		pass

	return os.path.join(outputdir, output_file)

# 分割音声ファイルのprefix
def getSplitAudioFilePrefix(input_file):
	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（これをフォルダ名などにする）
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	output_prefix = "{}_".format(base)
	return os.path.join(outputdir, output_prefix)

# 分割結果ファイル
def getSplitResultFile(input_file):
	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（これをフォルダ名などにする）
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	output_file = "_{}_split.txt".format(base)

	return os.path.join(outputdir, output_file)

# 認識結果ファイル
def getRecognizeResultFile(input_file):
	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（これをフォルダ名などにする）
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	outputdir = os.path.join(basedir, base) # 各種ファイルの出力先ディレクトリ

	output_file = "_{}.csv".format(base)

	return os.path.join(outputdir, output_file)

# マージ結果(csv)
def getMergedCsvFile(input_file):
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	return os.path.join(basedir, "merged.csv")

# マージ結果(js)
def getMergedJsFile(input_file):
	basedir = os.path.dirname(input_file) # 入力音声ファイルの置いてあるディレクトリ
	return os.path.join(basedir, "merged.json.js")

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