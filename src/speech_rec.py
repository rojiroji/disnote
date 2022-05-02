import speech_recognition as sr
import os
import sys
from collections import deque
import common
import traceback
import codecs

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'speech_rec'
CONFIG_WORK_PROGRESS = 'speech_rec_progress'
CONFIG_WORK_CONV_READY = 'speech_rec_conv_ready'

# 音声ファイルをtxtファイルに出力された結果に従って分割
def main(input_file):

	logger.info("3.音声認識開始")

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
	logger.info("音声ファイル：{}".format(input_file))

	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（話者）

	# 音声認識
	r = sr.Recognizer()
	num = 0

	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(split_result_file))

	recognize_result_file = common.getRecognizeResultFile(input_file)
	logger.info("認識結果ファイル：{}".format(recognize_result_file))

	split_result_queue = deque()

	with open(split_result_file, "r") as f:
		file_data = f.readlines()
		for line in file_data:
			split_result_queue.append(line.split("\t"))


	with codecs.open(recognize_result_file , mode, "CP932", 'ignore') as f:

		logger.info("音声認識中… ")
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

			try:
				with sr.AudioFile(tmp_audio_file) as source:
					audio = r.record(source)
			except FileNotFoundError:
				break
			
			text = ""
			confidence = 0

			try:
				result = r.recognize_google(audio, language='ja-JP', show_all=True)
				if len(result) > 0:
					alternative = result["alternative"]
					
					if "confidence" in alternative[0]:
						confidence = alternative[0]["confidence"]
					else:
						confidence = 0
					
					text = ""
					for alt in alternative:
						text = "\"" + alt["transcript"] + "\"," + text # ダブルクォーテーションで囲む
						
			except sr.UnknownValueError: # 認識したが文字起こしできなかった場合
				text = ""
				confidence = 0
			except:
				logger.error(traceback.format_exc()) # 音声認識失敗。ログを吐いた後にファイル名だけわかるように再度例外を投げる
				raise RuntimeError("音声認識に失敗したファイル … {},{}".format(audio_file_prefix, id))

			logger.debug("recog_end")


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

	logger.info("音声認識終了！")

# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
