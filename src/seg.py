import os
import sys
from inaSpeechSegmenter import Segmenter
from inaSpeechSegmenter.export_funcs import seg2csv, seg2textgrid
import subprocess
import common

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = 'seg'

def main(input_file):

	logger.info("1. 無音解析開始")

	config = common.readConfig(input_file)
	if config['DEFAULT'].get(CONFIG_WORK_KEY) == common.DONE:
		logger.info("完了済みのためスキップ(無音解析)")
		return


	# 音声ファイルを無音で分割して秒数とかを出力

	# 入力の音声ファイルのパスを引数で指定
	logger.info("音声ファイル：{}".format(input_file))
	
	# 音声の長さを取得(ffprobe実行)
	logger.info("音声ファイル読み込み中…")
	res = subprocess.check_output("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{}\"".format(input_file))
	duration = float(res.strip()) * 1000 # 再生時間(ミリ秒)
	logger.info("無音解析処理中… ({}sec)".format(int(duration/1000)))

	# 一定時間ごとに分割
	index = 0
	start_time = 0
	split_len = common.getSegTmpAudioLength()
	tmp_audio_file = "log/tmp.flac" # 一時ファイル（面倒なので消さない）
	logger.info("分割単位：{}min".format(int(split_len/60/1000)))

	while start_time < duration:

		# 分析結果ファイル
		seg_result_file = common.getSegResultFile(input_file, index)
		logger.info("分析結果ファイル：{}".format(seg_result_file))
		logger.info("無音解析処理中… {}/{}".format(index + 1, int(duration/split_len) + 1))

		end_time = min(start_time + split_len, duration)
		
		# ffmpegで分割
		res = subprocess.check_output("ffmpeg -i \"{}\" -ss {} -t {} -vn -acodec flac -y {}".format(input_file,start_time/1000, (end_time-start_time)/1000,tmp_audio_file))

		# 区間検出実行
		seg = Segmenter(vad_engine='smn', detect_gender=False)
		segmentation = seg(tmp_audio_file)

		# csv(という名のタブ)出力
		seg2csv(segmentation, seg_result_file)
		
		start_time += split_len
		index = index + 1

	# 終了したことをiniファイルに保存
	config.set('DEFAULT',CONFIG_WORK_KEY ,common.DONE)
	common.writeConfig(input_file, config)

	logger.info("無音解析終了！")


# 直接起動した場合
if __name__ == "__main__":
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません")
		sys.exit(1)

	main(sys.argv[1])
