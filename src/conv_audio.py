import os
import sys
from collections import deque
import common
import traceback
from mutagen.easyid3 import EasyID3
import csv
import shutil

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'conv_audio'
CONFIG_WORK_CONV_READY = 'speech_rec_conv_ready'

# 音声ファイルをtxtファイルに出力された結果に従ってmp3に変換（htmlから再生する用）
def main(input_file):

	logger.info("4. 音声変換開始 - {}".format(os.path.basename(input_file)))

	config = common.readConfig(input_file)
#	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE: # 処理順によっては変換前のファイルが残っていることがあるので、完了済みでもreturnしない
#		logger.info("完了済みのためスキップ(音声変換)")
#		return
	if config['DEFAULT'].get(CONFIG_WORK_CONV_READY) != "1": # v1.4.0以前だと、mp3のファイル名を保持していない（flacをそのままHTMLで再生する）ためスキップ
		logger.info("認識処理時のDisNOTEのバージョンが古いためスキップ(音声変換)")
		return

	# (元々の)入力の音声ファイルのパスを指定
	logger.info("音声ファイル：{}".format(os.path.basename(input_file)))

	base = os.path.splitext(os.path.basename(input_file))[0] # 拡張子なしのファイル名（話者）
	
	# 最後にflacファイルを消すかどうか
	is_remove_temp_split_flac = common.isRemoveTempSplitFlac()
	logger.info("テンポラリファイル削除：{}".format(is_remove_temp_split_flac))

	# 分割結果ファイルの読み込み
	split_result_file = common.getSplitResultFile(input_file)
	logger.info("分割結果ファイル：{}".format(os.path.basename(split_result_file)))

	split_result_queue = deque()
	with open(split_result_file, "r") as f:
		file_data = f.readlines()
		for line in file_data:
			split_result_queue.append(line.split("\t"))

	# 認識結果ファイルの読み込み
	recognize_result_file = common.getRecognizeResultFile(input_file)
	logger.info("認識結果ファイル：{}".format(os.path.basename(recognize_result_file)))

	recognize_result_list = list()
	with open(recognize_result_file, "r") as f:
		rows = csv.reader(f)
		recognize_result_list.extend(rows)

	logger.info("音声変換中… {}".format(os.path.basename(input_file)))

	queuesize = len(split_result_queue)

	# 分割して出力する音声ファイルのフォルダとプレフィックスまで指定
	audio_file_prefix = common.getSplitAudioFilePrefix(input_file)

	while len(split_result_queue) > 0 and len(recognize_result_list) > 0:
		# 分割結果ファイルの読み込み
		split_result = split_result_queue.popleft() # ID,srcファイル名(flac),開始時間(冒頭無音あり),終了時間(末尾無音あり),長さ(無音あり),開始時間(冒頭無音なし),長さ(末尾無音なし)の順 _split.txt
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
		if os.path.exists(audio_file): # dstファイル(mp3)が存在する場合
			src_audio_file_mttime = os.stat(src_audio_file).st_mtime
			audio_file_mttime = os.stat(audio_file).st_mtime
			if (audio_file_mttime > src_audio_file_mttime): # ソースより後に作られたファイルならOK
				logger.debug("変換後のファイルが存在しているためスキップ:{}".format(audio_file))
				continue

			logger.debug("変換後のファイルが存在しているが、古いので作り直す:{}".format(audio_file))
		
		# 無音部分を省いてmp3に変換。いったんテンポラリファイルに吐く（ffmpegの処理中にプロセスが落ちると中途半端なファイルが残ってしまうのを防ぐ）
		tmp_audio_file = common.getTemporaryFile(input_file, __file__, "mp3")
		common.runSubprocess("ffmpeg -ss {} -t {} -i \"{}\" -vn -y \"{}\"".format((org_start_time - start_time)/1000, (org_end_time-org_start_time)/1000,src_audio_file,tmp_audio_file))
		logger.debug("ffmpeg -ss {} -t {} -i \"{}\" -vn -y \"{}\"".format((org_start_time - start_time)/1000, (org_end_time-org_start_time)/1000,src_audio_file,tmp_audio_file))
		logger.debug("mp3_end")

		# 分析した音声にタグをつける
		logger.debug("tag_start")
		try:
			audio = EasyID3(tmp_audio_file)
			
			audio['artist'] = audio['albumartist'] = base
			audio['title'] = "{:0=2}:{:0=2}:{:0=2} {}".format(int(org_start_time / 1000 / 60 / 60), int(org_start_time / 1000 / 60) % 60, int(org_start_time/ 1000) % 60, text)
			audio.save()
		except Exception as e:
			logger.info(e)
			pass
		logger.debug("tag_end")
		
		
		# テンポラリファイルからリネーム、上書き
		shutil.move(tmp_audio_file, audio_file)
		
		# 変換が終わったのでsrcファイル(flac)を削除する 
		if is_remove_temp_split_flac: 
			logger.debug("remove:{}".format(src_audio_file))
			os.remove(src_audio_file)

		# 100行ごとか、最後の1行に進捗を出す
		if (id % 100) == 0 or (len(split_result_queue) == 0):
			logger.info("　音声変換中… {} {}/{}".format(base, id , queuesize))

	# 終了したことをiniファイルに保存
	common.updateConfig(input_file, {
		CONFIG_WORK_KEY :common.DONE
	})

	logger.info("音声変換終了！ {}".format(os.path.basename(input_file)))


# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
