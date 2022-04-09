import sys
import os
import seg
import split
import speech_rec
import common
import merge
import traceback
import requests
import json

logger = common.getLogger(__file__)

logger.info("----------------------------------------")
logger.info("             DisNOTE {}".format(common.getVersion()))
logger.info("----------------------------------------")

try:
	if len(sys.argv) < 2:
		logger.error("ファイルが指定されていません。")
		sys.exit(1)
	
	# ffmpeg起動確認
	try:
		common.runSubprocess("ffmpeg -h")
		logger.info("ffmpeg 実行確認OK")
	except FileNotFoundError as e:
		logger.error(e)
		logger.error("ffmpegが見つかりません。ffmpegがDisNOTEと同じフォルダにあるか確認してください。")
		sys.exit(1)
	except Exception as e:
		logger.error(e)
		logger.error("ffmpegを実行できません。ffmpegがDisNOTEと同じフォルダにあるか確認してください。")
		sys.exit(1)


	# ffprobe起動確認
	try:
		common.runSubprocess("ffprobe -h")
		logger.info("ffprobe 実行確認OK")
	except FileNotFoundError as e:
		logger.error(e)
		logger.error("ffprobeが見つかりません。ffprobeがDisNOTEと同じフォルダにあるか確認してください。")
		sys.exit(1)
	except Exception as e:
		logger.error(e)
		logger.error("ffprobeを実行できません。ffprobeがDisNOTEと同じフォルダにあるか確認してください。")
		sys.exit(1)

	index = 1
	l = list()

	while index < len(sys.argv):
		input_file = sys.argv[index]
		basename = os.path.basename(input_file)
		
		logger.info("---- 作業開始：{} ----".format(basename))
		
		# フォーマット確認
		try:
			res = common.runSubprocess("ffprobe.exe -v error -show_streams -print_format json \"{}\"".format(input_file))
		except Exception as e:
			logger.error("フォーマット確認失敗。処理を中断します（{} は音声ファイルではないようです）。".format(input_file))
			sys.exit(1)
		
		# f = json.loads(res.stdout)
		# logger.info(f['streams'][0])

		# 無音解析
		try:
			seg.main(input_file)
		except Exception as e:
			tb = sys.exc_info()[2]
			logger.error(traceback.format_exc())
			logger.error("{} の無音解析(1)に失敗しました({})。".format(input_file,e.with_traceback(tb)))
			sys.exit(1)

		# 音声分割
		try:
			split.main(input_file)
		except Exception as e:
			tb = sys.exc_info()[2]
			logger.error(traceback.format_exc())
			logger.error("{} の音声分割(2)に失敗しました({})。".format(input_file,e.with_traceback(tb)))
			sys.exit(1)

		# 音声認識
		try:
			speech_rec.main(input_file)
		except Exception as e:
			tb = sys.exc_info()[2]
			logger.error(traceback.format_exc())
			logger.error("{} の音声認識(3)に失敗しました({})。".format(input_file,e.with_traceback(tb)))
			sys.exit(1)

		index += 1
		l.append(input_file)

	# 結果マージ
	try:
		merge.main(l)
	except Exception as e:
		tb = sys.exc_info()[2]
		logger.error(traceback.format_exc())
		logger.error("結果マージ(4)に失敗しました({})。".format(e.with_traceback(tb)))
		sys.exit(1)

finally: # バージョン確認する

	try:
		r = requests.get('https://roji3.jpn.org/disnote/version.cgi', timeout=1) # 公開されている最新のzipファイルのファイル名が返る
		
		if r.status_code == 200:
			version = "v" + r.text.replace("DisNOTE_","").replace(".zip","")
			zipVersion = version.replace("v","").split('.') # ファイル名からバージョンを取得
			thisVersion = common.getVersion().replace("v","").split('.')
			
			for i in range(3): # メジャー、マイナー、パッチ の順で数字で比較
				if int(zipVersion[i]) > int(thisVersion[i]): # 公開されているzipの方が新しい
					logger.info("----------------------------------------------------")
					logger.info("  新しいDisNOTE({}) が公開されているようです".format(version) )
					logger.info("  https://roji3.jpn.org/disnote/")
					logger.info("----------------------------------------------------")
					break
				if int(zipVersion[i]) < int(thisVersion[i]): # 公開されているzipの方が古い（普通は無いはず）
					break
		else:
			#logger.info("DisNOTE最新バージョンの取得に失敗：{}".format(r.status_code))
			pass

	except:
		#tb = sys.exc_info()[2]
		#logger.error(traceback.format_exc())
		pass # 何が起きても無視
		
