import sys
import os
import seg
import split
import speech_rec
import common
import merge
import traceback

logger = common.getLogger(__file__)

logger.info("----------------------------------------")
logger.info("             DisNOTE {}".format(common.getVersion()))
logger.info("----------------------------------------")

if len(sys.argv) < 2:
	logger.error("ファイルが指定されていません")
	sys.exit(1)

index = 1
l = list()

while index < len(sys.argv):
	input_file = sys.argv[index]
	basename = os.path.basename(input_file)
	
	logger.info("---- 作業開始：{} ----".format(basename))

	# 無音解析
	try:
		seg.main(input_file)
	except:
		logger.error(traceback.format_exc())
		logger.error("{} の無音解析(1)に失敗しました".format(input_file))
		sys.exit(1)

	# 音声分割
	try:
		split.main(input_file)
	except:
		logger.error(traceback.format_exc())
		logger.error("{} の音声分割(2)に失敗しました".format(input_file))
		sys.exit(1)

	# 音声認識
	try:
		speech_rec.main(input_file)
	except:
		logger.error(traceback.format_exc())
		logger.error("{} の音声認識(3)に失敗しました".format(input_file))
		sys.exit(1)

	index += 1
	l.append(input_file)

# 結果マージ
try:
	merge.main(l)
except:
	logger.error(sys.exc_info())
	logger.error("結果マージ(4)に失敗しました")
	sys.exit(1)


