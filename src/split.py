import os
import sys
from inaSpeechSegmenter import Segmenter
from inaSpeechSegmenter.export_funcs import seg2csv, seg2textgrid
from pydub import AudioSegment
from collections import deque
import common

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'split'

def main(input_file):
	# 音声ファイルをtxtファイルに出力された結果に従って分割
	logger.info("2. 音声分割開始")

	config = common.readConfig(input_file)
	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE:
		logger.info("完了済みのためスキップ(音声分割)")
		return


	# 入力の音声ファイルのパスを指定
	logger.info("音声ファイル：{}".format(input_file))

	type = os.path.splitext(os.path.basename(input_file))[1][1:] # 拡張子(読み込み時のフォーマット指定)

	# 分析結果ファイル
	seg_result_file = common.getSegResultFile(input_file)
	logger.info("分析結果ファイル：{}".format(seg_result_file))

	# 分割して出力する音声ファイルのフォルダとプレフィックスまで指定
	audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

	segmentation = deque()

	# 分析結果ファイル（タブ区切り）を開く

	with open(seg_result_file , "r") as f:
		connect = False
		prev_noEnergy_length = 0 # 前回の無音部分の長さ
		prev_length = 0 # 前回の長さ
		index = 0

		logger.info ("分析結果ファイル読み込み中…")
		
		f.readline() # ヘッダを読み捨て
		file_data = f.readlines()
		for line in file_data:
			segment = line.split("\t")
			
			index += 1
			#logger.info ("分析結果ファイル読み込み中… {}".format(index))

			segment_label = segment[0]

			# 区間の開始時刻の単位を秒からミリ秒に変換
			start_time = float(segment[1]) * 1000
			end_time = float(segment[2]) * 1000


			if (segment_label != 'noEnergy'):  # 無音区間以外。noiseも捨てていいかも。 'speech' noEnergyで、startとendの間が1未満の場合は、前の項目と繋げていいかも。1回目のstartと2回目のendを採用する。
				if connect: # 1つ前と連結させる
					prev = segmentation.pop()
					start_time = prev[1]
				else: # 今回が音がある部分の冒頭
					start_time -= min(prev_noEnergy_length, 500) # 前回の無音部分の0.5秒を頭に入れる
				
				connect = False
				prev_length = end_time - start_time
				
				mlength = 2 * 60 * 1000 # N分ごとに区切る(これ以上長いと音声認識がエラーを返す可能性がある)
				while True :
					length = end_time - start_time
					
					if length < mlength:
						segmentation.append([segment_label, start_time, end_time ]) # push(末尾)
						break
					else:
						segmentation.append([segment_label, start_time, start_time + mlength]) # push(3分)
						start_time += mlength
						logger.debug("length > mlength: length={}".format(length))

			else: # 無音区間
				length = end_time - start_time
				prev_noEnergy_length = length
				connect = False
				if len(segmentation) > 0:
					if length < 1 * 1000 and length + prev_length < 5 * 1000: # 無音がX秒未満(息継ぎとかを無視したい)、Y秒未満の場合(長すぎにならないようにする)は、次の音声と接続させる
						connect = True
						logger.debug("connect. len:{}".format(length))
					else:
						prev = segmentation.pop() # 無音がX秒以上の場合は、前の音声が確定する。前の音声の終了時間を伸ばす（最後に無音がつく。最大5秒とする。5秒でいいかは微妙）⇒認識が遅くなるが、こっちの方が精度がいい
						prev[2] += min(length, 5000) 
						segmentation.append(prev) # push


	# 音声を分割する
	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(split_result_file))

	with open(split_result_file , "w") as f:# 分割結果ファイルに結果書き込み+音声書き込み
		audio_all = AudioSegment.from_file(input_file, format=type)
		speech_segment_index = 0
		index = 0

		logger.info ("音声分割中… ")
		
		for segment in segmentation:
			# segmentはタプル
			# タプルの第1要素が区間のラベル
			segment_label = segment[0]

			index = index + 1
			logger.debug ("音声分割中… {}/{}".format(index, len(segmentation)))
			
			if (segment_label != 'noEnergy'):  # 無音区間以外にする。noiseは捨てていいかも。 

				start_time = segment[1]
				end_time = segment[2]
				
				filename = "{}{}.flac".format(audio_file_prefix , speech_segment_index)

				# 分割結果をflacに出力
				newAudio = audio_all[start_time:end_time]
				newAudio.export(filename, format="flac")

				# 分割結果の時間やファイル名など
				f.write("{}	{}	{}	{}	{}\n".format(speech_segment_index, filename, start_time, end_time, end_time - start_time))
				
				speech_segment_index += 1

	# 終了したことをiniファイルに保存
	config.set('DEFAULT',CONFIG_WORK_KEY ,common.DONE)
	common.writeConfig(input_file, config)

	logger.info("音声分割終了！")

# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
