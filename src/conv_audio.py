import os
import sys
from collections import deque
import common
import traceback
from mutagen.easyid3 import EasyID3
import csv

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'conv_audio'
CONFIG_WORK_CONV_READY = 'speech_rec_conv_ready'

# 音声ファイルをtxtファイルに出力された結果に従って分割
def main(input_file):

	logger.info("4.音声変換開始")

	config = common.readConfig(input_file)
	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE:
		logger.info("完了済みのためスキップ(音声変換)")
		return
	if config['DEFAULT'].get(CONFIG_WORK_CONV_READY) != "1": # v1.4.0以前だと、mp3のファイル名を保持していない（flacをそのままHTMLで再生する）ためスキップ
		logger.info("認識処理時のDisNOTEのバージョンが古いためスキップ(音声変換)")
		return

	# (元々の)入力の音声ファイルのパスを指定
	logger.info("音声ファイル：{}".format(input_file))

	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（話者）

	# 分割結果ファイルの読み込み
	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(split_result_file))

	split_result_queue = deque()
	with open(split_result_file, "r") as f:
		file_data = f.readlines()
		for line in file_data:
			split_result_queue.append(line.split("\t"))

	# 認識結果ファイルの読み込み
	recognize_result_file = common.getRecognizeResultFile(input_file)
	logger.info("認識結果ファイル：{}".format(recognize_result_file))

	recognize_result_list = list()
	with open(recognize_result_file, "r") as f:
		rows = csv.reader(f)
		recognize_result_list.extend(rows)

	logger.info("音声変換中… ")
	queuesize = len(split_result_queue)

	# 分割して出力する音声ファイルのフォルダとプレフィックスまで指定
	audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

	while len(split_result_queue) > 0:
		# 分割結果ファイルの読み込み
		split_result = split_result_queue.popleft() # ID,srcファイル名(flac),開始時間(冒頭無音あり),終了時間(末尾無音あり)の順 _split.txt
		id = int(split_result[0])
		src_audio_file = split_result[1]
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
		
		# 認識結果ファイルの読み込み
		recognize_result = recognize_result_list.pop(0) # 話者,dstファイル名(mp3),開始時間(冒頭無音なし),長さ(末尾無音なし), スコア, 認識結果 の順
		audio_file = recognize_result[1]
		text = recognize_result[5]

		# htmlファイルからの再生用に出力
		if os.path.exists(src_audio_file) == False: # srcファイル(flac)が存在しない場合はスキップ（既に変換が完了して削除済みとみなす）
			logger.debug("ソースファイル削除済みのためスキップ:{}".format(src_audio_file))
			continue

		logger.debug("mp3_start")
		common.runSubprocess("ffmpeg -i \"{}\" -ss {} -t {} -vn -y \"{}\"".format(src_audio_file,(start_time - org_start_time)/1000, (org_end_time-org_start_time)/1000,audio_file))
		logger.debug("mp3_end")

		# 分析した音声にタグをつける
		logger.debug("tag_start")
		try:
			audio = EasyID3(audio_file)
			
			audio['artist'] = audio['albumartist'] = base
			audio['title'] = "{:0=2}:{:0=2}:{:0=2} {}".format(int(org_start_time / 1000 / 60 / 60), int(org_start_time / 1000 / 60) % 60, int(org_start_time/ 1000) % 60, text)
			audio.save()
		except Exception as e:
			logger.info(e)
			pass
		logger.debug("tag_end")
		
		# 変換が終わったのでsrcファイル(flac)を削除する
		os.remove(src_audio_file)

		# 100行ごとか、最後の1行に進捗を出す
		if (id % 100) == 0 or (len(split_result_queue) == 0):
			logger.info("　音声変換中… {} {}/{}".format(base, id , queuesize))

	# 終了したことをiniファイルに保存
	config.set('DEFAULT',CONFIG_WORK_KEY ,common.DONE)
	common.writeConfig(input_file, config)

	logger.info("音声変換終了！")

# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
