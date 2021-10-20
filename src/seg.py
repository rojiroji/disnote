import os
import sys
from inaSpeechSegmenter import Segmenter
from inaSpeechSegmenter.export_funcs import seg2csv, seg2textgrid
from pydub import AudioSegment
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

	# 分析結果ファイル
	seg_result_file = common.getSegResultFile(input_file)
	logger.info("分析結果ファイル：{}".format(seg_result_file))

	logger.info("無音解析処理中…")
	seg = Segmenter(vad_engine='smn', detect_gender=False)

	# 区間検出実行
	segmentation = seg(input_file)

	# csv(という名のタブ)出力
	seg2csv(segmentation, seg_result_file)

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
