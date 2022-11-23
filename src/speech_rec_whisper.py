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
import csv

class RequestError(Exception): pass

logger = common.getLogger(__file__)

model = None
CONFIG_WORK_KEY = 'speech_rec_whisper'
CONFIG_WORK_PROGRESS = 'speech_rec_progress_whisper'
CONFIG_WORK_CONV_READY = 'speech_rec_conv_ready_whisper'
CONFIG_WORK_MODEL = 'speech_rec_whisper_model'

# 音声分割情報
def getCuttimeInfoSub(start,end):
	cuttime = dict()
	cuttime["start_time"] = start
	cuttime["end_time"]   = end
	cuttime["duration"]   = end - start
	logger.info("認識用再分割：{}-{}({})".format(cuttime["start_time"] ,cuttime["end_time"], cuttime["duration"] ))
	return cuttime

# 音声分割情報
def getCuttimeInfo(cuttime_start, length, split_result_list):
	cuttime_end   = None
	cuttime_end_prev = None

	for split in split_result_list:
		# Whisper認識用に分割する時間の設定
		cuttime_end   = split["org_end_time"]

		if cuttime_end - cuttime_start > length: # 規定値より長くなった場合、その1つ前まででカット
			if cuttime_end_prev is not None:
				logger.debug("認識用再分割（※通常）")
				return getCuttimeInfoSub(cuttime_start, cuttime_end_prev)
			
			# 1回で規定値より長くなった場合、これで切るしかない
			logger.debug("認識用再分割（※いきなり規定値超えた）")
			return getCuttimeInfoSub(cuttime_start, cuttime_end)
			
		cuttime_end_prev = cuttime_end
	
	if cuttime_start is not None:
		logger.debug("認識用再分割（※最終）")
		return getCuttimeInfoSub(cuttime_start, cuttime_end_prev)
	
	return None

# 音声ファイルの認識を行うかどうか。行わないなら理由（ログに出力する文字列）を返す。行うならNoneを返す。
def reasonNotToRecognize(input_file):
	modelname = common.getWhisperModel()
	config = common.readConfig(input_file)

	# モデルの指定が過去の結果と異なる場合はやり直す。初回もTrueになるはず。
	model_changed = (config['DEFAULT'].get(CONFIG_WORK_MODEL) != modelname)

	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE and (not model_changed):
		return "完了済みのためスキップ(音声認識)"

	if modelname == common.WHISPER_MODEL_NONE:
		return "Whisperを使用しない設定のためスキップ"

	return None

# Whisper（バイナリ版）の認識結果を返す
def getBinaryWhisperResultToSegments(whisper_result):
	
	lines = whisper_result.split("\n")
	l = 1 # 最初に空行があるので1行飛ばす

	segment_list = list()
	while l < len(lines): # 開始時間(秒),終了時間(秒),text,token(text),token(id),区切り行 の順
		segment = dict()

		line = lines[l].strip()
		if len(line) <= 0:
			break
		segment["start"] = float(line) / 1000
		l += 1
		
		line = lines[l].strip()
		segment["end"] = float(line) / 1000
		l += 1
		
		line = lines[l].strip()
		segment["text"] =line
		l += 1
		#print(line)

		l += 3 # token(text),token(id),区切り行 を読み飛ばし
		
		segment_list.append(segment)
	
	return segment_list

# 音声ファイルをtxtファイルに出力された結果に従って分割
def main(input_file):
	global model
	
	logger.info("3. 音声認識開始(Whisper) - {}".format(os.path.basename(input_file)))
	
	func_in_time = time.time()

	reason = reasonNotToRecognize(input_file) # 認識せずにスキップするパターン
	if reason is not None:
		logger.info(reason)
		return

	modelname = common.getWhisperModel()
	language  = common.getWhisperLanguage()
	logger.info("Whisperモデル：{}".format(modelname))

	is_use_binary = common.isUseBinaryWhisper() # バイナリ版を使うかどうか
	logger.info("Whisper：{}".format("バイナリ版" if is_use_binary else "Python版"))

	config = common.readConfig(input_file)
	
	# モデルの指定が過去の結果と異なる場合はやり直す。初回もTrueになるはず。
	model_changed = (config['DEFAULT'].get(CONFIG_WORK_MODEL) != modelname)
	
	if not common.isValidWhisperModel():
		raise ValueError("Whisperのモデル名が不正({})：DisNOTE.iniの{}の設定を確認してください".format(modelname,common.WHISPER_MODEL))
	

	# Whisperモデル読み込み（python版。読み込みを1回にするためにglobalに保持）
	if (model is None) and (not is_use_binary):
		logger.info("Cuda.available:{}".format(torch.cuda.is_available()))
		
		# pyinstallerでバイナリを作った場合、lib以下にwhisperのassetsが存在しないため手元からコピーする
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

		logger.info("Whisperモデル読み込み開始：{}".format(modelname))
		model = whisper.load_model(modelname) #, device="cpu"
		logger.info("Whisperモデル読み込み完了：{}".format(modelname))

	# 中断データ
	progress = config['DEFAULT'].get(CONFIG_WORK_PROGRESS,'')

	# 中断データがあった場合は続きから、そうでない場合は最初から
	segment_file = common.getSegmentFileWhisper(input_file) 
	if len(progress) > 0 and (not model_changed):
		logger.info("認識途中のデータがあったため再開({})".format(progress))
	else:
		common.updateConfig(input_file, {
			CONFIG_WORK_PROGRESS : ""
		})
		progress = ""
		with codecs.open(segment_file , "w", "CP932", 'ignore') as f: # 最初からの場合は、中間ファイルを消してしまう(後で読み込むので空のファイルにしておく)
			pass

	# (元々の)入力の音声ファイルのパスを指定
	logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（話者）

	#########
	# 方針
	# Whisperは小さい音声を大量に認識させると処理時間が非常に長くなるので、split_audioで分割した音声ではなくもっと大きく区切った音声を認識させる
	#########

	# 分割結果ファイルの読み込み
	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))

	split_result_list = list()
	cut_len_max = common.getWhisperBinaryDuration() if is_use_binary else common.getWhisperTmpAudioLength() # バイナリ版かどうかで、作業ごとの音声の長さを決める
	cut_len = cut_len_max
	last_endtime = 0
	logger.info("分割単位：{}min".format(int(cut_len/60/1000)))

	with open(split_result_file, "r") as f:
		logger.info("分割結果確認中… {}".format(base))
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

			logger.debug("split {}({}-{})".format(index,split["org_start_time"],split["org_end_time"] ))

			split_result_list.append(split)
			last_endtime = split["end_time"] 
			index += 1

	# 中断データがあったら、認識結果と処理再開時間を読み込み
	segment_map = dict() # 認識結果のマップ。認識開始時間（ミリ秒）がキー
	cuttime_start = None
	
	if len(progress) > 0:
		cuttime_start = int(progress) # 中断データまでスキップ

		# 現時点での認識結果読み込み
		with codecs.open(segment_file , "r", "CP932", 'ignore') as f:
			rows = csv.reader(f)

			for row in rows:
				start_time = int(row[0]) # ミリ秒
				end_time   = int(row[1])  # ミリ秒
				text = row[2]
				
				# 認識開始時間,認識終了時間,テキスト の順
				segment_result = dict()
				segment_result["start_time"] = start_time
				segment_result["end_time"]   = end_time
				segment_result["duration"]   = end_time - start_time
				segment_result["text"] = text
				logger.debug("　認識結果読み込み：{}-{}:{}".format(segment_result["start_time"] , segment_result["end_time"] , segment_result["text"] ))
				
				# 認識開始時間をキーにして登録する
				segment_map[start_time] = segment_result
					
	elif len(split_result_list) > 0: # 最初から
		cuttime_start = split_result_list[0]["org_start_time"]

	# 作業用音声ファイル
	if is_use_binary:
		tmp_audio_file = common.getTemporaryFile(input_file, __file__, "wav") # バイナリ版は16bitのwavしかよめない
		res = common.runSubprocess("ffmpeg -i \"{}\" -vn  -ar 16000 -ac 1 -c:a pcm_s16le -y \"{}\" "
			.format(input_file,tmp_audio_file)) # Whisper(バイナリ版)の中でseekするので、音声ファイルは先に作っておく
	else:
		tmp_audio_file = common.getTemporaryFile(input_file, __file__, "flac")
	
	# 音声認識
	index = 0
	prev_index = 0
	while cuttime_start is not None:
		cuttime = getCuttimeInfo(cuttime_start, cut_len, split_result_list)
		if cuttime is None:
			break

		# 音声認識用に分割
		if is_use_binary:
			pass
		else:
			process = "ffmpeg -ss {} -t {} -i \"{}\" -vn -acodec flac -y \"{}\"".format(cuttime["start_time"]/1000, cuttime["duration"]/1000,input_file,tmp_audio_file)
			#logger.info(process)
			res = common.runSubprocess(process)

		
		# 音声認識
		# Whisperは音声認識結果が時々おかしくなる（同じ認識結果で認識時間が1000の倍数、という結果を何度も繰り返す）ので、おかしかったら中断する
		# Whisperのバージョンが上がれば状況が変わるかもしれない。
		logger.info("　音声認識中 {} ({}%) {}/{} binary:{}".format(base, int(100 * cuttime_start / last_endtime), cuttime_start, last_endtime, is_use_binary))
		
		if is_use_binary: # バイナリ版Whisper実行（wav化した元データを認識）
			process = "{} -l {} -m {} -t 0  -ot {} -d {} -vb \"{}\" \"{}\" ".format(
				os.path.join("whisper","main.exe"),language, 	os.path.join("whisper", "ggml-{}.bin".format(modelname)),
				cuttime["start_time"], cuttime["duration"], split_result_file,tmp_audio_file)
				
			logger.debug(process)
			res = common.runSubprocess(process)
			
			logger.info(res.stderr)

			result = dict()
			result["segments"] = getBinaryWhisperResultToSegments(res.stdout)
			result["text"] = ""

		else: # python版Whisper実行（細切れにした音声を認識）
			result = model.transcribe(tmp_audio_file, language=language) # , verbose=True
		
		logger.debug("音声認識結果(Whisper) {}".format(result["text"]))

		prev_text = ""
		check_count = 0
		is_allok = True
		last_ok = None

		for segment in result["segments"]:
			#print("id:{}, seek:{}, start:{}, end:{}, text:{}".format(segment["id"],segment["seek"],segment["start"],segment["end"],segment["text"]))
			segment_result = dict()
			segment_result["start_time"] = int(float(segment["start"]) * 1000)  # 秒単位小数なのでミリ秒に直す
			segment_result["end_time"]   = int(float(segment["end"])   * 1000)  # 秒単位小数なのでミリ秒に直す
			segment_result["duration"]   = segment_result["end_time"] - segment_result["start_time"]
			segment_result["text"] = segment["text"]
			logger.info("segment_result({}-{}:{}){}".format(segment_result["start_time"],segment_result["end_time"],segment_result["duration"],segment_result["text"]))
			
			# 同じ認識結果で、認識時間が1000の倍数だったらチェック、連続したらリトライ
			if (segment_result["text"] == prev_text) and (segment_result["duration"] % 1000 == 0):
				check_count += 1
				logger.debug("　音声認識 同じ結果が繰り返された {} check_count={},result={}".format(base, check_count, segment_result))
				if check_count >= 2: # バイナリ版と条件を揃える
					logger.info("　※音声認識結果が良くない {} start_time={}".format(base, segment_result["start_time"]))
					is_allok = False
					break
			else:
				check_count = 0
				last_ok = segment_result
			
			if is_use_binary:
				pass
			else:
				segment_result["start_time"] += cuttime["start_time"] # python版Whisperは音声ファイルを分割してから認識しているので、分割開始時間だけずらす
				segment_result["end_time"]   += cuttime["start_time"] # python版Whisperは音声ファイルを分割してから認識しているので、分割開始時間だけずらす
				
			prev_text = segment_result["text"]
			segment_map[segment_result["start_time"] ] = segment_result # マップに登録（同じ時間の結果は上書きされる）

		# segment_mapを保存 
		with codecs.open(segment_file , "w", "CP932", 'ignore') as f:
			for start_time in sorted(segment_map.keys()):
				segment_result = segment_map[start_time]

				text = "\"" + segment_result["text"] + "\"" # ダブルクォーテーションで囲む
				f.write("{},{},{}\n".format(segment_result["start_time"] , segment_result["end_time"] , text )) 

				if last_ok == segment_result: # おかしな結果は保存しない
					break

		# 認識結果の時間と分割結果の時間を比べる(WhisperとinaSpeechSegmenterで有声と判定された時間帯が異なるので、inaSpeechSegmenterの方に寄せなければならない)
		split_index = 0
		for start_time in sorted(segment_map.keys()):
			segment_result = segment_map[start_time]
			split_index = 0
			overlap_duration = None
			split_overlap = None
			split = split_result_list[0]
			
			for index in range(0, len(split_result_list)):
				split = split_result_list[index]
				
				# 重なり判定
				left  = max(segment_result["start_time"] , split["org_start_time"] )
				right = min(segment_result["end_time"]   , split["org_end_time"] )
				duration = right - left
				logger.debug("duration:{}({}-{})".format(duration, right, left))
				
				if duration >= 0: # 重なった
					pass
				elif  segment_result["end_time"] <  split["org_start_time"]: # 重ならないまま追い抜かれてしまった
					if split_overlap is not None:
						break
					logger.debug("追い抜かれた(index={}):start_time:{} duration:{}<{} text:{}".format(index,segment_result["start_time"] ,overlap_duration, duration,segment_result["text"]))
				else:
					if split_overlap is not None: # さっきまで重なっていたのに、また重ならなくなったら終了
						break
					continue

				# より深く重なったら、そのsplitが候補
				if (overlap_duration is None) or (overlap_duration < duration):
					if (overlap_duration is not None) and (overlap_duration > 0):
						logger.debug("候補入れ替え(index={}):start_time:{} duration:{}<{} text:{}".format(index,segment_result["start_time"] ,overlap_duration, duration,segment_result["text"]))
					split_index = index
					overlap_duration = duration
					split_overlap = split
				
			if split_overlap is None:
				split_index = len(split_result_list) - 1
				split_overlap = split
				logger.debug("重なりなし:start_time:{} text:{}".format(segment_result["start_time"] ,segment_result["text"]))

			# split_overlap["text"] += segment_result["text"] + " "
			segment_result["split_index"] = split_index # 認識結果と重なる分割結果のindexを保持
			logger.debug("checked(index={}):start_time:{} overlap_duration:{} text:{}".format(index,segment_result["start_time"] , overlap_duration,segment_result["text"]))
			
			if last_ok == segment_result: # おかしな結果は処理をスキップする
				break


		# 次の分割開始位置（次回は、全部認識成功していたら最後に認識した区分領域の次から、そうでなければ最後に認識した分割区域から、認識する）
		next_index = split_index
		cut_len_prev = cut_len

		logger.info("index:prev_index:{} split_index:{},is_allok:{}".format(prev_index,split_index,is_allok))
		if is_allok: 
			next_index += 1
			cut_len = min(cut_len_prev + 60 * 1000, cut_len_max) # 成功したら認識する音声を長くする（初期値よりは大きくしない）
		else:
			if prev_index >= next_index: # 無限ループを防ぐため、開始位置だけは必ずずらす
				logger.debug("無限ループ防止:prev_index:{} next_index:{}".format(prev_index,next_index))
				next_index = prev_index + 1
			cut_len = max(cut_len_prev - 60 * 1000, 60 * 1000) # 失敗したら認識する音声を短くする
		logger.debug("　次回分割長： {} → {}".format(cut_len_prev, cut_len))
		
		if next_index < len(split_result_list):
			cuttime_start = split_result_list[next_index]["org_start_time"]
			logger.debug("次回：index:prev_index:{} split_index:{},next_index:{},is_allok:{} cuttime_start:{}".format(prev_index,split_index,next_index,is_allok,cuttime_start))
			
			prev_index = next_index
		else:
			break # 最後まで行った

		# ここまで完了した、と記録
		common.updateConfig(input_file, {
			CONFIG_WORK_PROGRESS : str(cuttime_start),
			CONFIG_WORK_MODEL:modelname # モデルを記録しておく
		})

	os.remove(tmp_audio_file) # 作業用の音声ファイルを消す

	# 認識結果のテキストをsplitに反映
	for start_time in sorted(segment_map.keys()):
		segment_result = segment_map[start_time]
		if "split_index" in segment_result:
			split_index = segment_result["split_index"] # 認識結果と重なる分割結果のindex
			split_result_list[split_index]["text"] += segment_result["text"] + " "

	# 最終結果書き込み
	recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
	logger.info("認識結果ファイル(Whisper)：{}".format(os.path.basename(recognize_result_file)))
	audio_file_prefix = common.getSplitAudioFilePrefix(input_file)
	with codecs.open(recognize_result_file , "w", "CP932", 'ignore') as f:

		for split in split_result_list:
			confidence = 0

			audio_file = "{}{}.mp3".format(audio_file_prefix , split["id"])
			org_start_time = split["org_start_time"]
			org_end_time   = split["org_end_time"]
			text = "\"" + split["text"] + "\"" # ダブルクォーテーションで囲む
			confidence = 0

			f.write("{},{},{},{},{},{}\n".format(base, audio_file, org_start_time, org_end_time-org_start_time, int(confidence * 100), text)) 


	# 終了したことをiniファイルに保存
	common.updateConfig(input_file, {
		CONFIG_WORK_PROGRESS : "",
		CONFIG_WORK_KEY : common.DONE,
		CONFIG_WORK_MODEL:modelname, # モデルを記録しておく
		CONFIG_WORK_CONV_READY : "1"  # 再生用に変換してもOK
	})

	func_out_time = time.time()
	logger.info("音声認識終了！(Whisper) {} ({:.2f}min)".format(os.path.basename(input_file), (func_out_time - func_in_time) / 60))



# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
