import speech_recognition as sr
import os
import sys
from collections import deque
import common
import traceback
import codecs
from mutagen.flac import FLAC

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'speech_rec'
CONFIG_WORK_PROGRESS = 'speech_rec_progress'

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
		
		while len(split_result_queue) > 0:
			split_result = split_result_queue.popleft() # ID,ファイル名,開始時間,終了時間の順
			id = int(split_result[0]) + 1
			audio_file = split_result[1]
			start_time = int(float(split_result[2]))
			length = int(float(split_result[4]))
			
			num += 1
			
			if len(progress) > 0: # 中断データまでスキップ
				if audio_file == progress:
					progress = '' # 追いついたので、次の行から続き
				continue
			
			try:
				with sr.AudioFile(audio_file) as source:
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
						
			except sr.UnknownValueError:
				text = ""
				confidence = 0
			except:
				logger.error(traceback.format_exc()) # 音声認識失敗。ログを吐いた後にファイル名だけわかるように再度例外を投げる
				raise RuntimeError("音声認識に失敗したファイル … {}".format(audio_file))
			
			# 分析した音声にタグをつける
			try:
				audio = FLAC(audio_file)
				
				audio['artist'] = audio['album artist'] = audio['albumartist'] = audio['ensemble'] = base
				audio['comment'] = audio['description'] = text
				audio['title'] = "{:0=2}:{:0=2}:{:0=2} {}".format(int(start_time / 1000 / 60 / 60), int(start_time / 1000 / 60) % 60, int(start_time/ 1000) % 60, text)
				audio.pprint()
				audio.save()
			except:
				pass

			logger.debug("音声認識中… {},{},{}".format(id, int(confidence * 100), text))
			if (id % 10) == 0 or (len(split_result_queue) == 0): # 10行ごとか、最後の1行に進捗を出す
				logger.info("　音声認識中… {}/{}".format(id , queuesize))
			
#			if len(text) > 0: # 認識結果が無くても追加することにした # ↓TODO：https://qiita.com/butada/items/33db39ced989c2ebf644
			f.write("{},{},{},{},{},{}\n".format(base, audio_file, start_time, length, int(confidence * 100), text)) 
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
	common.writeConfig(input_file, config)

	logger.info("音声認識終了！")

# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
