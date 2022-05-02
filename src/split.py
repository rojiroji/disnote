import os
import sys
from inaSpeechSegmenter import Segmenter
from inaSpeechSegmenter.export_funcs import seg2csv, seg2textgrid
from collections import deque
import common

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'split'

def main(input_file):
	# 音声ファイルをtxtファイルに出力された結果に従って分割
	logger.info("2. 音声分割開始 - {}".format(os.path.basename(input_file)))

	config = common.readConfig(input_file)
	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE:
		logger.info("完了済みのためスキップ(音声分割)")
		return


	# 入力の音声ファイルのパスを指定
	logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

	type = os.path.splitext(os.path.basename(input_file))[1][1:] # 拡張子(読み込み時のフォーマット指定)

	# 分析結果ファイルを順に開く
	seg_resultfile_index = 0
	segmentation = deque()
	connect = False
	prev_fixed = False
	prev_noEnergy_length = 0 # 前回の無音部分の長さ
	prev_length = 0 # 前回の長さ
	index = 0

	logger.info ("分析結果ファイル読み込み中…")
	
	isRecognizeNoize = common.isRecognizeNoize()
	logger.info("ノイズ部分も認識対象にするかどうか：{}".format(isRecognizeNoize))
	
	while True:
		seg_result_file = common.getSegResultFile(input_file, seg_resultfile_index)

		# 分析結果ファイルがなければ終了
		if os.path.exists(seg_result_file) == False:
			break

		logger.info("分析結果ファイル：{}({})".format(os.path.basename(seg_result_file), seg_resultfile_index + 1))

		# 分析結果ファイル（タブ区切り）を開く
		with open(seg_result_file , "r") as f:

			segment_label = ""
			
			f.readline() # ヘッダを読み捨て
			
			file_data = f.readlines()
			for line in file_data:
				segment = line.split("\t")
				
				index += 1
				#logger.info ("分析結果ファイル読み込み中… {}".format(index))
				
				segment_label = segment[0]

				# 区間の開始時刻の単位を秒からミリ秒に変換 + ファイル番号によって補正
				start_time = float(segment[1]) * 1000 + float(common.getSegTmpAudioLength() * seg_resultfile_index)
				end_time   = float(segment[2]) * 1000 + float(common.getSegTmpAudioLength() * seg_resultfile_index)
				org_start_time = start_time
				org_end_time = end_time

				# 認識対象とするかどうか
				is_target = False
				if (isRecognizeNoize): # 無音区間以外を認識対象とする
					if (segment_label != 'noEnergy'):  # 無音区間以外なら認識対象とする（noiseなども対象）
						is_target = True
				else:
					if (segment_label == 'speech'):#  'speech' のみ認識対象とする
						is_target = True

				
				if is_target:
					if connect: # 1つ前と連結させる
						prev = segmentation.pop()
						start_time = prev["start_time"]
						org_start_time = prev["org_start_time"]
					else: # 今回が音がある部分の先頭
						start_time -= min(prev_noEnergy_length, 500) # 前回の無音部分の0.5秒を頭に入れる
					
					connect = False
					prev_fixed = False
					prev_length = end_time - start_time
					
					mlength = 2 * 60 * 1000 # N分ごとに区切る(これ以上長いと音声認識がエラーを返す可能性がある)
					while True :
						length = end_time - start_time
						
						if length < mlength:
							segmentation.append({
								"segment_label"	: segment_label,
								"start_time"	: start_time,
								"end_time"		: end_time,
								"org_start_time": org_start_time,
								"org_end_time"	: org_end_time
							}) # push(音声の末尾部分)
							break
						else:
							segmentation.append({
								"segment_label"	: segment_label,
								"start_time"	: start_time,
								"end_time"		: start_time + mlength,
								"org_start_time": org_start_time,
								"org_end_time"	: start_time + mlength
							}) # push(N分)
							start_time += mlength
							org_start_time = start_time
							logger.debug("length > mlength: length={}".format(length))

				else: # 無音区間
					length = end_time - start_time
					prev_noEnergy_length = length
					connect = False
					if len(segmentation) > 0:
						if length < 1 * 1000 and length + prev_length < 5 * 1000: # 無音がX秒未満(息継ぎとかを無視したい)、Y秒未満の場合(長すぎにならないようにする)は、次の音声と接続させる
							connect = True
							logger.debug("connect. len:{}".format(length))
						elif prev_fixed == False:
							prev = segmentation.pop() # 無音がX秒以上の場合は、前の音声が確定する。前の音声の終了時間を伸ばす（最後に無音がつく。最大5秒とする。5秒でいいかは微妙）⇒認識が遅くなるが、こっちの方が精度がいい
							prev["end_time"] += min(length, 5000) 
							segmentation.append(prev) # push
							prev_fixed = True # 何度も連結しないようにする
							logger.debug("prev_fixed. {},{}".format(prev["start_time"],prev["end_time"]))

		seg_resultfile_index += 1 # 次のファイルへ
		if (segment_label != 'noEnergy'): # 音声ありの状態でファイルが閉じた場合、次のファイルと連結させるために長さ0の無音区間を作る
			t = common.getSegTmpAudioLength() * seg_resultfile_index
			segmentation.append({
				"segment_label"	: 'noEnergy',
				"start_time"	: t,
				"end_time"		: t,
				"org_start_time": t,
				"org_end_time"	: t
			})
			logger.debug("ファイルの区切りで無音追加：{}({})".format(seg_resultfile_index, t))


	# 音声を分割する
	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))
	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（話者）

	with open(split_result_file , "w") as f:# 分割結果ファイルに結果書き込み+音声書き込み
		speech_segment_index = 1
		index = 0

		# 分割して出力する音声ファイルのフォルダとプレフィックスまで指定
		audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

		logger.info ("音声分割中… {}".format(base))
		
		for segment in segmentation:
			# segmentはタプル
			# タプルの第1要素が区間のラベル
			segment_label = segment['segment_label']

			index = index + 1
			# logger.debug ("音声分割中… {}/{}".format(index, len(segmentation)))
			
			if (index % 100) == 0 or (len(segmentation) == index): # 100行ごとか、最後の1行で進捗を出す
				logger.info("　音声分割中… {} {}/{}".format(base, index, len(segmentation)))

			if (segment_label != 'noEnergy'):  # 無音区間以外の部分だけを出力する

				start_time = segment["start_time"]
				end_time = segment["end_time"]
				org_start_time = segment["org_start_time"]
				org_end_time = segment["org_end_time"]
				
				filename = "{}{}.flac".format(audio_file_prefix , speech_segment_index)

				# 分割結果をflacに出力
				res = common.runSubprocess("ffmpeg -i \"{}\" -ss {} -t {} -vn -acodec flac -y \"{}\"".format(input_file,start_time/1000, (end_time-start_time)/1000,filename))


				# 分割結果の時間やファイル名など
				f.write("{}	{}	{}	{}	{}	{}	{}\n".format(speech_segment_index, filename, start_time, end_time, end_time - start_time, org_start_time, org_end_time))
				
				speech_segment_index += 1

	# 終了したことをiniファイルに保存
	config.set('DEFAULT',CONFIG_WORK_KEY ,common.DONE)
	common.writeConfig(input_file, config)

	logger.info("音声分割終了！ {}".format(os.path.basename(input_file)))


# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
