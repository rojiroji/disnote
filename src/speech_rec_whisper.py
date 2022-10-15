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

class RequestError(Exception): pass

logger = common.getLogger(__file__)

model = None
CONFIG_WORK_KEY = 'speech_rec_whisper'
CONFIG_WORK_PROGRESS = 'speech_rec_progress_whisper'
CONFIG_WORK_CONV_READY = 'speech_rec_conv_ready_whisper'
CONFIG_WORK_MODEL = 'speech_rec_whisper_model'

# 音声ファイルをtxtファイルに出力された結果に従って分割
def main(input_file):
	global model
	
	logger.info("3. 音声認識開始(whisper) - {}".format(os.path.basename(input_file)))
	logger.info("Cuda.available:{}".format(torch.cuda.is_available()))
	
	func_in_time = time.time()

	modelname = common.getWhisperModel()
	language  = common.getWhisperLanguage()
	logger.info("whisperモデル：{}".format(modelname))

	config = common.readConfig(input_file)
	
	# モデルの指定が過去の結果と異なる場合はやり直す。初回もTrueになるはず。
	model_changed = (config['DEFAULT'].get(CONFIG_WORK_MODEL) != modelname)
	
	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE and (not model_changed):
		logger.info("完了済みのためスキップ(音声認識)")
		return
	
	if modelname == common.WHISPER_MODEL_NONE:
		logger.info("whisperを使用しない設定のためスキップ")
		return
	
	if not common.isValidWhisperModel():
		raise ValueError("whisperのモデル名が不正({})：DisNOTE.iniの{}の設定を確認してください".format(modelname,common.WHISPER_MODEL))
	

	# whisperモデル読み込み（読み込みを1回にするためにglobalに保持）
	if model is None:
		# pyinstallerでバイナリを作った場合、whisperのassetsが存在しないためコピーする
		if os.path.exists("whisper/assets"): # assetsフォルダがある場合
			assetsdir = os.path.join(os.path.dirname(whisper.__file__), "assets")
			logger.debug("assetsdir:{}".format(assetsdir))
			if os.path.exists(assetsdir): # 通常であればここにassetsディレクトリがあるはず
				logger.debug("whisperのディレクトリにassetsディレクトリあり")
			else:
				logger.info("assetsディレクトリをコピー")
				shutil.copytree("whisper/assets",assetsdir)
		else:
			logger.debug("currentにassetsなし")

		logger.info("whisperモデル読み込み開始：{}".format(modelname))
		model = whisper.load_model(modelname)
		logger.info("whisperモデル読み込み完了：{}".format(modelname))

	if model is None:
		logger.info("whisperのモデルが指定されていないためスキップ(音声認識)")
		return
	
	# 中断データ
	progress = config['DEFAULT'].get(CONFIG_WORK_PROGRESS,'')

	# 中断データがあった場合は続きから、そうでない場合は最初から
	mode = 'w'
	if len(progress) > 0 and (not model_changed):
		logger.info("認識途中のデータがあったため再開({})".format(progress))
		mode = 'a'

	# (元々の)入力の音声ファイルのパスを指定
	logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（話者）

	# 分割結果ファイルの読み込み
	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))

	split_result_list = list()

	with open(split_result_file, "r") as f:
		logger.info ("分割結果確認中… {}".format(base))
		index = 0

		file_data = f.readlines()
		for line in file_data:
			split = dict()
			
			# ID,分割した音声ファイル名(flac),開始時間(冒頭無音あり),終了時間(末尾無音あり),長さ(無音あり),開始時間(冒頭無音なし),長さ(末尾無音なし)の順 _split.txt
			data = line.split("\t")
			split["id"] = data[0]
			split["filename"]   = data[1]
			split["start_time"] = int(float(data[2]))
			split["end_time"]   = int(float(data[3]))

			split["org_start_time"] = split["start_time"] 
			split["org_end_time"]   = split["end_time"]
			try:
				split["org_start_time"] = int(float(data[5]))
				split["org_end_time"]   = int(float(data[6]))
			except IndexError:
				pass
							
			split["index"] = index
			split["text"] = ""

			logger.debug("split({}-{}){}".format(split["start_time"],split["end_time"],split["id"] ))

			split_result_list.append(split)
			index += 1
		logger.info ("分割結果確認完了(size:{}) {}".format(len(split_result_list),base))


	# 音声認識
	recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
	logger.info("認識結果ファイル(whisper)：{}".format(os.path.basename(recognize_result_file)))

	with codecs.open(recognize_result_file , mode, "CP932", 'ignore') as f:
		rec_result_list = list()

		# 音声認識
		logger.info("　音声認識中… {} {}/{}".format(base, 1 , 1)) # TODO：分割してループ回す。split["start_time"]とsplit["end_time"]を基準にする。
		result = model.transcribe(input_file, language=language) # , verbose=True
		
		logger.debug("音声認識結果(whisper) {}".format(result["text"]))

		for segment in result["segments"]:
			#print("id:{}, seek:{}, start:{}, end:{}, text:{}".format(segment["id"],segment["seek"],segment["start"],segment["end"],segment["text"]))
			segment_result = dict()
			segment_result["start_time"] = int(float(segment["start"]) * 1000) # 秒単位 1.0 のようなフォーマットなのでミリ秒に直す
			segment_result["end_time"]   = int(float(segment["end"])   * 1000) # 秒単位 1.0 のようなフォーマットなのでミリ秒に直す
			segment_result["duration"]   = segment_result["end_time"] - segment_result["start_time"]
			segment_result["text"] = segment["text"]
			rec_result_list.append(segment_result)
			logger.debug("segment_result({}-{}:{}){}".format(segment_result["start_time"],segment_result["end_time"],segment_result["duration"],segment_result["text"]))

		# 認識結果の時間と、分割結果の時間を比べる
		split_index = 0
		for segment_result in rec_result_list:
			isOverlap = False
			overlapDuration = None
			overlapSplit = None
			split = split_result_list[0]
			
			for index in range(split_index, len(split_result_list)):
				split = split_result_list[index]
				
				# 重なり判定
				left  = max(segment_result["start_time"] , split["start_time"] )
				right = min(segment_result["end_time"]   , split["end_time"] )
				duration = right - left
				logger.debug("duration:{}({}-{})".format(duration, right, left))
				
				if duration >= 0: # 重なった
					pass
				elif  segment_result["end_time"] <  split["start_time"]: # 重ならないまま追い抜かれてしまった
					if overlapSplit is not None:
						break
					logger.debug("追い抜かれた(index={}):start_time:{} duration:{}<{} text:{}".format(index,segment_result["start_time"] ,overlapDuration, duration,segment_result["text"]))
				else:
					if isOverlap: # さっきまで重なっていたのに、また重ならなくなったら終了
						break
					continue

				# より深く重なったら、そのsplitが候補
				isOverlap = True
				if (overlapDuration is None) or (overlapDuration < duration):
					if (overlapDuration is not None) and (overlapDuration > 0):
						logger.debug("候補入れ替え(index={}):start_time:{} duration:{}<{} text:{}".format(index,segment_result["start_time"] ,overlapDuration, duration,segment_result["text"]))
					split_index = index
					overlapDuration = duration
					overlapSplit = split

			if overlapSplit is None:
				overlapSplit = split
				logger.debug("重なりなし:start_time:{} text:{}".format(segment_result["start_time"] ,segment_result["text"]))

			overlapSplit["text"] += segment_result["text"] + " "
			logger.debug("checked(index={}):start_time:{} overlapDuration:{} text:{}".format(index,segment_result["start_time"] , overlapDuration,segment_result["text"]))


		# 書き込み
		audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

		for split in split_result_list:
			confidence = 0

			audio_file = "{}{}.mp3".format(audio_file_prefix , split["id"])
			org_start_time = split["org_start_time"]
			org_end_time   = split["org_end_time"]
			text = "\"" + split["text"] + "\"" # ダブルクォーテーションで囲む
			confidence = 0

			f.write("{},{},{},{},{},{}\n".format(base, audio_file, org_start_time, org_end_time-org_start_time, int(confidence * 100), text)) 

			# ここまで完了した、と記録
			#common.updateConfig(input_file, {
			#	CONFIG_WORK_PROGRESS : audio_file,
			#	CONFIG_WORK_MODEL:modelname # モデルを記録しておく
			#})
		f.flush()


	if len(progress) > 0: # 中断したまま終わってしまった
		common.updateConfig(input_file, {
			CONFIG_WORK_PROGRESS : ""
		})
		raise RuntimeError("音声認識再開失敗。再度実行してください。")
		return
		

	# 終了したことをiniファイルに保存
	common.updateConfig(input_file, {
		CONFIG_WORK_PROGRESS : "",
		CONFIG_WORK_KEY : common.DONE,
		CONFIG_WORK_MODEL:modelname, # モデルを記録しておく
		CONFIG_WORK_CONV_READY : "1"  # 再生用に変換してもOK
	})

	func_out_time = time.time()
	logger.info("音声認識終了！(whisper) {} ({:.2f}min)".format(os.path.basename(input_file), (func_out_time - func_in_time) / 60))



# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
