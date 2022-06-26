import os
import sys
from collections import deque
import common
import traceback
import codecs
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
class RequestError(Exception): pass

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'speech_rec_witai'
CONFIG_WORK_PROGRESS = 'speech_rec_progress_witai'
CONFIG_WORK_CONV_READY = 'speech_rec_conv_ready_witai'

# 音声ファイルをtxtファイルに出力された結果に従って分割
def main(input_file):

	logger.info("3. 音声認識開始(wit.ai) - {}".format(os.path.basename(input_file)))
	func_in_time = time.time()

	if len(common.getWitAiServerAccessToken()) == 0:
		logger.info("wit.aiのトークンが設定されていないためスキップ(音声認識)")
		return

	config = common.readConfig(input_file)
	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE:
		logger.info("完了済みのためスキップ(音声認識)")
		return

	# 中断データ
	progress = config['DEFAULT'].get(CONFIG_WORK_PROGRESS,'')
	
	# 中断データがあった場合は続きから、そうでない場合は最初から
	mode = 'w'
	if len(progress) > 0:
		logger.info("認識途中のデータがあったため再開({})".format(progress))
		mode = 'a'

	# (元々の)入力の音声ファイルのパスを指定
	logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（話者）

	# 音声認識
	num = 0

	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))

	recognize_result_file = common.getRecognizeResultFileWitAI(input_file)
	logger.info("認識結果ファイル(wit.ai)：{}".format(os.path.basename(recognize_result_file)))

	split_result_queue = deque()

	with open(split_result_file, "r") as f:
		file_data = f.readlines()
		for line in file_data:
			split_result_queue.append(line.split("\t"))


	with codecs.open(recognize_result_file , mode, "CP932", 'ignore') as f:

		logger.info("音声認識中(wit.ai)… {}".format(base))
		queuesize = len(split_result_queue)

		# 分割して出力する音声ファイルのフォルダとプレフィックスまで指定
		audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

		while len(split_result_queue) > 0:
			split_result = split_result_queue.popleft() # ID,ファイル名,開始時間,終了時間の順
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
			
			audio_file = "{}{}.mp3".format(audio_file_prefix , id)

			if len(progress) > 0: # 中断データまでスキップ
				if audio_file == progress:
					progress = '' # 追いついたので、次の行から続き
				continue

			logger.debug("recog_start")

			ss = 0 # wit.ai は最初の息継ぎで認識をやめてしまう（っぽい）ので、認識をやめた後の部分の音声を切り出して繰り返し認識する
			text = ""
			confidence = 0
			
			checkNext = True
			count = 1
			
			tmp_witai_basefile = "log/tmp_wit_base.wav" # wit.aiが読めるように変換
			common.runSubprocess("ffmpeg -i \"{}\"  -ar 16000 -ac 1 -bits_per_raw_sample 16 -sample_fmt s16 -y \"{}\"".format(tmp_audio_file,tmp_witai_basefile))

			while checkNext:
				checkNext = False
				try:
					# wit.aiに渡す音声を作成する。認識されていない部分だけを切り出す。
					tmp_witai_file = "log/tmp_wit.wav"
					
					split_begin = time.time()
					common.runSubprocess("ffmpeg  -ss {} -i \"{}\" -ss 0 -y \"{}\"".format( ss/1000 ,tmp_witai_basefile,tmp_witai_file))
					split_end  = time.time()
					logger.debug("split {:.3f}".format(split_end - split_begin))
					
					result = recognize_wit(tmp_witai_file, key=common.getWitAiServerAccessToken())
					if "text" in result and len(result["text"]) > 0:
						logger.debug(json.dumps(result))
						
						result_text = result["text"] + " "
						
						if "speech" in result and "tokens" in result["speech"]:
							start = 0
							end = 0
							for token in result["speech"]["tokens"]:
								if "start" in token:
									start = max(token["start"],end)  # tokenが2つ以上ある場合は、最後のミリ秒を返す
								if "end" in token:
									end = max(token["end"],end)  # tokenが2つ以上ある場合は、最後のミリ秒を返す
								logger.debug("start={},end={}".format(start,end))
							
							if end > 0: # 稀にend==0が返ることがあるので、end > 0 の場合のみ再認識する
								checkNext = True
								logger.debug("ss={},end={} -> ss={}".format(ss,end,ss+end))
								ss += end
								count += 1
							
							if start == 0 and len(text) > 0: # 前回の結果の末尾の部分をもう一度認識してしまった場合は省略(時々必要な結果まで捨ててしまうので要検討)
								result_text = ""
								logger.debug("skipped.")
							
						text = text + result_text # 結果を後ろに繋げていく

				except:
					logger.error(traceback.format_exc()) # 音声認識失敗。ログを吐いた後にファイル名だけわかるように再度例外を投げる
					raise RuntimeError("音声認識に失敗したファイル(wit.ai) … {},{}".format(audio_file_prefix, id))

			text = "\"" + text.strip() + "\"" # ダブルクォーテーションで囲む

			logger.debug("recog_end.count={}".format(count))


			logger.debug("音声認識中… {}, {},{},{}".format(base, id, int(confidence * 100), text))
			if (id % 10) == 0 or (len(split_result_queue) == 0): # 10行ごとか、最後の1行に進捗を出す
				logger.info("　音声認識中… {} {}/{}".format(base, id , queuesize))
			
			f.write("{},{},{},{},{},{}\n".format(base, audio_file, org_start_time, org_end_time-org_start_time, int(confidence * 100), text)) 
			f.flush()
			config.set('DEFAULT',CONFIG_WORK_PROGRESS ,audio_file) # ここまで完了した、と記録
			common.writeConfig(input_file, config)


	if len(progress) > 0: # 中断したまま終わってしまった
		config.set('DEFAULT',CONFIG_WORK_PROGRESS ,"")
		common.writeConfig(input_file, config)
		raise RuntimeError("音声認識再開失敗。再度実行してください。")
		return
		
	# 終了したことをiniファイルに保存
	config.set('DEFAULT',CONFIG_WORK_PROGRESS ,"")
	config.set('DEFAULT',CONFIG_WORK_KEY ,common.DONE)
	config.set('DEFAULT',CONFIG_WORK_CONV_READY ,"1") # 再生用に変換してもOK
	common.writeConfig(input_file, config)

	func_out_time = time.time()
	logger.info("音声認識終了！(wit.ai) {} ({:.2f}min)".format(os.path.basename(input_file), (func_out_time - func_in_time) / 60))


# wit.aiで音声認識
prev_witai_requesttime = 0

def recognize_wit(target_file, key):
	global prev_witai_requesttime

	with open (target_file,'rb') as payload:
		
		url = "https://api.wit.ai/speech?v=20220608" # TODO vをwit.ai用の設定ファイルに
		request = Request(url, data=payload, headers={"Authorization": "Bearer {}".format(key), "Content-Type": "audio/wav "})
		try:
			# 1分につき60回の頻度制限があるので、前回実行時の時間から1秒待つ（実際に1秒以内に完了することはまずないが、一応）
			current = time.time()

			wait = (prev_witai_requesttime + 1) - current
			logger.debug("wait={}".format(wait))
			if(wait > 0):
				time.sleep(wait)
				
			request_start = time.time()
			response = urlopen(request, timeout=None)

			prev_witai_requesttime = time.time()
			request_end = prev_witai_requesttime
			
			logger.debug("request {:.3f}".format(request_end - request_start))
		except HTTPError as e:
			raise RequestError("recognition request failed: {} / DisNOTE.initのwit_ai_server_access_tokenの値が正しいか確認してください。".format(e.reason))
		except URLError as e:
			raise RequestError("recognition connection failed: {}".format(e.reason))
		response_text = response.read().decode("utf-8")
		logger.debug(response_text)
		
		result = dict(text = "")
		result_json = ""
		for text in response_text.split('\n'):
			result_json += text.strip()
			if text[0] == '}': # json形式の出力が何度も繰り返される。indentがついているので、0文字目が '}' の場合はjsonが閉じたということ
				result = json.loads(result_json)
				logger.debug("result_json={}".format(result_json))
				if ("is_final" in result) and result["is_final"]: # is_finalフラグが立っていたら完了（最後の出力がこうなるはずだが一応フラグを見る）
					logger.debug("result={}".format(result))
					return result
				result_json = ""

		logger.debug("result(none)={}".format(result))
		return result


# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
