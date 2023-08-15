import os
import sys
import common
import csv
import json
import pathlib
import shutil
from dateutil.parser import parse
from dateutil.parser import ParserError
from dateutil.relativedelta import relativedelta
import datetime
import codecs
import hashlib

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = "merge"


def main(input_files, arg_files):
    logger.info("5. 結果マージ開始")

    personalData = {}  # 話者情報
    basedir = os.path.dirname(arg_files[0])  # 出力先のディレクトリ（＝入力音声ファイルの置いてあるディレクトリ）

    # 出力ファイル用のハッシュ値を、入力ファイルから決定する
    input_files.sort()  # 入力ファイル名をソート（引数の順番だけ違う場合にファイル名を揃えるため）
    join_hash = ""
    for input_file in input_files:
        config = common.readConfig(input_file)
        hash = config["DEFAULT"].get("hash")
        join_hash += hash + "_"

        key = common.getFileNameWithoutExtension(input_file)
        personalData[key] = {
            "orgfile": os.path.basename(input_file),
            "hash": hash,
            "name": key,
            "displayname": key,
            "show": "true",
        }

    project_hash = hashlib.md5(join_hash.encode()).hexdigest()  # 出力ファイル用のハッシュ値

    # 出力するファイル名の決定
    basefilename = ""
    if len(arg_files) == 1:  # 1つのファイルを元に解析されていた場合は、そのファイルを使う
        basefilename = common.getFileNameWithoutExtension(arg_files[0]) + "_disnote"
        mixed_mediafile = arg_files[0]
    else:
        basefilename = (
            project_hash[:8] + "_disnote"
        )  # ファイル名はハッシュ値の先頭8文字だけ採用（まあ被らないでしょう…）

    # MIXされたメディアファイルの作成
    mixed_media_ismovie = False
    created_mixed_media = False
    if len(arg_files) == 1:  # 1つのファイルを元に解析されていた場合は、そのファイルをそのまま使う
        mixed_mediafile = arg_files[0]
        try:
            ffprobe_result = common.getFileFormat(mixed_mediafile)
            streams = json.loads(ffprobe_result)
            for stream_index, stream in enumerate(streams["streams"]):
                if stream["codec_type"] == "video":  # 動画ファイルかどうかをチェック
                    mixed_media_ismovie = True
                    break
        except Exception as e:
            logger.info(e)
            logger.log("{}のフォーマット確認中にエラー。".format(mixed_mediafile))

    else:  # 複数ファイルの場合はffmpegでmixする
        mixed_mediafile = os.path.join(basedir, basefilename + ".mp3")
        option_input = ""
        for input_file in input_files:
            option_input += ' -i "{}" '.format(input_file)

        if os.path.exists(mixed_mediafile):
            logger.info("最終結果ファイル(mp3)出力（既に存在するためスキップ）")
        else:
            logger.info("最終結果ファイル(mp3)出力開始")
            common.runSubprocess(
                'ffmpeg {}  -y -filter_complex "amix=inputs={}:duration=longest:dropout_transition=0:normalize=0" "{}" '.format(
                    option_input, len(input_files), mixed_mediafile
                )
            )
        created_mixed_media = True

    # 認識結果ファイル(csv)を読み込んでマージする
    whispermodelname = common.getWhisperModel()

    resultMap = dict()
    for input_file in input_files:
        count = 0
        recognize_result_file = common.getRecognizeResultFile(input_file)
        count += mergeRecognizeResult(recognize_result_file, resultMap, "G")

        recognize_result_file = common.getRecognizeResultFileWitAI(input_file)
        count += mergeRecognizeResult(recognize_result_file, resultMap, "W")

        recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
        count += mergeRecognizeResult(
            recognize_result_file, resultMap, whispermodelname[0]
        )  # tiny,base,small,medium,largeのいずれかの先頭1文字（小文字）

        # 発言がない人物は話者一覧から外す
        if count <= 0:
            key = common.getFileNameWithoutExtension(input_file)
            personalData.pop(key)
            continue

    l = list(resultMap.values())
    l.sort(key=lambda x: int(x[2]))  # 3列目（発話タイミング）でソート

    # ファイルパスを相対パスにする
    for line in l:
        p = pathlib.Path(line[1])
        line[1] = str(p.relative_to(basedir))

    # csvファイル出力
    merged_csv_file = os.path.join(basedir, basefilename + ".csv")
    logger.info("最終結果ファイル(csv)出力開始")

    with open(merged_csv_file, "w", newline="") as f:  # 変な改行が入るのを防ぐため newline=''
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(
            [
                "話者",
                "ファイル",
                "時間（ミリ秒）",
                "長さ(ミリ秒)",
                "音声認識エンジン",
                "候補1",
                "候補2",
                "候補3",
                "候補4",
                "候補5",
                "候補6",
            ]
        )
        # ヘッダ
        writer.writerows(l)

    logger.info("最終結果ファイル(html)出力開始")

    # Craigのinfo.txtを探す
    baseDate = None
    try:
        infoFile = os.path.join(basedir, "info.txt")
        with open(infoFile, "r", encoding="utf-8") as f:
            for line in f:
                segment = line.split("\t")
                if len(segment) > 1 and segment[0] == "Start time:":  # 開始時刻があれば読む
                    baseDate = parse(segment[1])
                    break
    except ParserError:
        logger.info("　info.txtのStart time: parse失敗")
    except FileNotFoundError:
        logger.info("　info.txtなし")
    except:
        logger.info("　info.txtの読み込み失敗")

    # index.htmlのオリジナル読み込み
    with open("src/index.html", "r") as f:
        index_data = f.read()

    # JavaScriptの変数部分を作成
    merged_js = "results = {};\n".format(json.dumps(l, indent=4, ensure_ascii=False))
    merged_js += "personalData = {};\n".format(
        json.dumps(personalData, indent=4, ensure_ascii=False)
    )
    merged_js += 'projectHash = "{}";\n'.format(project_hash)
    merged_js += 'mixedMediafile = "{}";\n'.format(
        pathlib.Path(mixed_mediafile).relative_to(basedir)
    )
    merged_js += "mixedMediaIsMovie = {};\n".format(
        "true" if mixed_media_ismovie else "false"
    )
    merged_js += 'version = "{}";\n'.format(common.getVersion())

    if baseDate:
        baseDate += relativedelta(hours=+9)
        merged_js += "baseDate=new Date({},{},{},{},{},{});\n".format(
            baseDate.year,
            baseDate.month,
            baseDate.day,
            baseDate.hour,
            baseDate.minute,
            baseDate.second,
        )

    # index.html の値の部分を置換
    index_data = index_data.replace(
        "TITLE", basefilename.replace("_disnote", "")
    ).replace("RESULTS", merged_js)

    # index.html書き込み
    with open(
        os.path.join(basedir, basefilename + ".html"), "w", newline=""
    ) as f:  # 変な改行が入るのを防ぐため newline=''
        f.write(index_data)

    # htmlファイルなどをコピー
    # shutil.copyfile("src/index.html", os.path.join(basedir, "index.html"))
    shutil.copytree(
        "src/htmlfiles", os.path.join(basedir, "htmlfiles"), dirs_exist_ok=True
    )

    # プレイリスト作成(ファイルパスだけ書く)
    logger.info("最終結果ファイル(m3u8)出力開始")
    with codecs.open(
        os.path.join(basedir, basefilename + ".m3u8"), "w", "utf8", "ignore"
    ) as f:
        for line in l:
            f.write(line[1])
            f.write("\n")

    logger.info("すべての処理が完了しました！")
    logger.info("【出力ファイル】")
    logger.info("　{}.html".format(basefilename))
    logger.info("　{}.csv".format(basefilename))
    logger.info("　{}.m3u8".format(basefilename))
    if created_mixed_media:
        logger.info("　{}.mp3".format(basefilename))


# 認識結果ファイル(csv)を読み込んでマージする(行数を返す)
def mergeRecognizeResult(recognize_result_file, resultMap, engine):
    TEXT_INDEX = 5
    try:
        logger.debug("認識結果ファイル：{}".format(os.path.basename(recognize_result_file)))
        with open(recognize_result_file, "r") as f:
            rows = csv.reader(f)

            for row in rows:
                audio_file = row[
                    1
                ]  # 2列目（音声ファイル名(分割したファイル）をキーにする。バージョンによって拡張子が異なるので拡張子以降は省略）
                ppos = audio_file.rfind(".")
                key = audio_file[0:ppos]
                engineStr = engine * (len(row) - TEXT_INDEX)

                if key in resultMap.keys():
                    if len(row[TEXT_INDEX]) <= 0:
                        continue
                    del row[0:TEXT_INDEX]  # 認識結果は6列目以降にある。認識結果以外の要素を削除

                    dst_result = resultMap[key]
                    dst_result[TEXT_INDEX:TEXT_INDEX] = row  # 認識結果を混ぜる
                    dst_result[4] = engineStr + dst_result[4]
                else:
                    row[4] = engineStr
                    resultMap[key] = row

            return rows.line_num

    except FileNotFoundError:
        logger.info(
            "認識結果ファイルなし（スキップ）：{}".format(os.path.basename(recognize_result_file))
        )

    return 0


# 直接起動した場合
if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("ファイルが指定されていません")
        sys.exit(1)

    index = 1
    l = list()
    while index < len(sys.argv):
        l.append(sys.argv[index])
        index += 1

    main(l)
