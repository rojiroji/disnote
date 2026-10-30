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
import codecs
import hashlib
from janome.tokenizer import Tokenizer

logger = common.getLogger(__file__)

CONFIG_WORK_KEY = "merge"
# 読み候補は大文字IDにして、モデルごとの通常候補と区別する
READING_ENGINE_IDS = {
    "t": "T",
    "b": "B",
    "s": "S",
    "m": "M",
}
# 単語辞書で変換した候補のエンジンID（モデルごとに数字を割り当てる）
DICTIONARY_ENGINE_IDS = {
    "t": "1",
    "b": "2",
    "s": "3",
    "m": "4",
    "l": "5",
}
DICTIONARY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trpg_dictionary.csv")


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
            common.logForGui(logger, "merge_mp3")
            common.runSubprocess(
                'ffmpeg {}  -y -filter_complex "amix=inputs={}:duration=longest:dropout_transition=0:normalize=0" "{}" '.format(
                    option_input, len(input_files), mixed_mediafile
                )
            )
        created_mixed_media = True

    # 認識結果ファイル(csv)を読み込んでマージする
    whispermodelname = common.getWhisperModel()
    # 全候補で共有し、読み候補の形態素解析に使う
    tokenizer = Tokenizer()
    # 単語辞書（現状はソースと同じフォルダ固定。後で引数指定にする予定）
    word_dict = loadWordDictionary(DICTIONARY_FILE)

    resultMap = dict()
    for input_file in input_files:
        count = 0

        recognize_result_file = common.getRecognizeResultFileWhisper(input_file)
        count += mergeRecognizeResult(
            recognize_result_file, resultMap, whispermodelname[0], tokenizer, word_dict
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

    with codecs.open(merged_csv_file, "w", "CP932", "ignore") as f:  # 変な改行が入るのを防ぐため newline=''
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
    with codecs.open("src/index.html", "r", "CP932", "ignore") as f:
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
    default_title = basefilename.replace("_disnote", "")
    index_data = index_data.replace("TITLE", default_title).replace(
        "RESULTS", merged_js
    )

    # index.html書き込み
    htmlfile = os.path.join(basedir, basefilename + ".html")
    with codecs.open(htmlfile, "w", "CP932", "ignore") as f:  # 変な改行が入るのを防ぐため newline=''
        f.write(index_data)

    # htmlファイルなどをコピー
    # shutil.copyfile("src/index.html", os.path.join(basedir, "index.html"))
    shutil.copytree(
        "src/htmlfiles", os.path.join(basedir, "htmlfiles"), dirs_exist_ok=True
    )

    # jsファイル書き込み(GUI版で使う)
    jsfile = os.path.join(basedir, basefilename + ".js")
    with codecs.open(jsfile, "w", "CP932", "ignore") as f:  # 変な改行が入るのを防ぐため newline=''
        f.write(merged_js)

    # プレイリスト作成(ファイルパスだけ書く)
    logger.info("最終結果ファイル(m3u8)出力開始")
    with codecs.open(
        os.path.join(basedir, basefilename + ".m3u8"), "w", "utf8", "ignore"
    ) as f:
        for line in l:
            f.write(line[1])
            f.write("\n")

    # 終了ログ
    common.logForGui(logger, "merge_end", info={"result": os.path.abspath(jsfile)})

    logger.info("すべての処理が完了しました！")
    logger.info("【出力ファイル】")
    logger.info("　{}.html".format(basefilename))
    logger.info("　{}.js".format(basefilename))
    logger.info("　{}.csv".format(basefilename))
    logger.info("　{}.m3u8".format(basefilename))
    if created_mixed_media:
        logger.info("　{}.mp3".format(basefilename))

# 文字列が整数かどうかの判定
def isInt(s):  # 整数値を表しているかどうかを判定
    try:
        int(s, 10)  # 文字列を実際にint関数で変換してみる
    except ValueError:
        return False
    else:
        return True

# 認識結果ファイル(csv)を読み込んでマージする(行数を返す)
def mergeRecognizeResult(recognize_result_file, resultMap, engine, tokenizer, word_dict):
    TEXT_INDEX = 5
    try:
        logger.debug("認識結果ファイル：{}".format(os.path.basename(recognize_result_file)))
        colcount = 0
        with codecs.open(recognize_result_file, "r", "CP932", "ignore") as f:
            rows = csv.reader(f)
            colcount += 1

            for row in rows:
                audio_file = row[
                    1
                ]  # 2列目（音声ファイル名(分割したファイル）をキーにする。バージョンによって拡張子が異なるので拡張子以降は省略）
                ppos = audio_file.rfind(".")
                key = audio_file[0:ppos]
                # 候補1の読みを追加し、さらに単語辞書で変換した結果を新しい候補1にする
                # （元の候補1と読みは、候補2と候補3にずれる）。エンジンIDも対応させる
                candidate_count = len(row) - TEXT_INDEX
                reading = toHiragana(row[TEXT_INDEX], tokenizer)
                converted = convertWithDictionary(row[TEXT_INDEX], tokenizer, word_dict)
                row.insert(TEXT_INDEX + 1, reading)
                row.insert(TEXT_INDEX, converted)
                engineStr = (
                    DICTIONARY_ENGINE_IDS[engine]
                    + engine
                    + READING_ENGINE_IDS[engine]
                    + engine * (candidate_count - 1)
                )
                
                isFormatError = False
                for rownum in [2,3,4]: # 3,4,5列目には数字が入っている。稀にファイル書き込みがおかしくて変な値が入っていることがある
                    try:
                        if isInt(row[rownum]) == False: 
                            logger.info("フォーマットエラー(ValueError)：{} {}:{}".format(os.path.basename(recognize_result_file),colcount,rownum))
                            isFormatError = True
                    except IndexError:
                        logger.info("フォーマットエラー(IndexError)：{} {}:{}".format(os.path.basename(recognize_result_file),colcount,rownum))
                        isFormatError = True
                        continue

                
                if isFormatError:
                    continue
                    
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


def kanaToHiragana(text):
    # カタカナ(ァ〜ヶ)だけをひらがなに変換する。それ以外の文字はそのまま
    return "".join(
        chr(ord(char) - 0x60) if "\u30a1" <= char <= "\u30f6" else char
        for char in text
    )


def tokenizeWithReading(text, tokenizer):
    # 形態素解析して、(表層形, ひらがなの読み, 品詞情報) のリストを返す
    result = []
    for token in tokenizer.tokenize(text):
        # 辞書にない語は読みが "*" になるので、表層形をそのまま読みとして使う
        reading = token.reading if token.reading != "*" else token.surface
        result.append(
            (token.surface, kanaToHiragana(reading), token.part_of_speech.split(","))
        )
    return result


def isJoinedToPrevious(prev_pos, pos):
    # 形態素が直前の形態素と一体の語（活用語尾・複合名詞など）かどうかを判定する
    # 一体の語の途中は、単語辞書の一致の開始位置・終了位置にしない
    if pos[0] == "助動詞" and prev_pos[0] in ("動詞", "形容詞", "助動詞"):  # 食べ|ます、行っ|た など
        return True
    if pos[0] == "助詞" and pos[1] == "接続助詞" and prev_pos[0] in ("動詞", "形容詞", "助動詞"):
        return True  # 食べ|て など
    if pos[0] == "動詞" and pos[1] == "非自立":  # 食べ|て|いる など
        return True
    if pos[0] == "名詞" and pos[1] in ("接尾", "非自立"):
        return True
    if prev_pos[0] == "接頭詞":
        return True
    if prev_pos[0] == "名詞" and pos[0] == "名詞":  # 複合名詞
        return True
    return False


def toHiragana(text, tokenizer):
    # 形態素ごとの読みをつなぎ、ひらがなに変換する
    return "".join(reading for _, reading, _ in tokenizeWithReading(text, tokenizer))


def loadWordDictionary(dictionary_file):
    # 単語辞書(Shift-JISのcsv)を読み込み、{読み(ひらがな): 単語} を返す
    # 1列目が読み(ひらがな/カタカナ)、2列目が単語、1行目はヘッダ
    word_dict = {}
    try:
        with codecs.open(dictionary_file, "r", "CP932", "ignore") as f:
            rows = csv.reader(f)
            next(rows, None)  # ヘッダ行を読み飛ばす
            for row in rows:
                if len(row) < 2:
                    continue
                reading = kanaToHiragana(row[0].strip())
                word = row[1].strip()
                if reading and word:
                    word_dict[reading] = word
        logger.info("単語辞書読み込み：{}件".format(len(word_dict)))
    except FileNotFoundError:
        logger.info("単語辞書なし（スキップ）：{}".format(dictionary_file))
    return word_dict


def convertWithDictionary(text, tokenizer, word_dict):
    # 候補1を形態素に分け、読みが単語辞書に一致する連続した形態素を辞書の単語に置き換える
    if not word_dict:
        return text
    max_len = max(len(reading) for reading in word_dict)
    tokens = tokenizeWithReading(text, tokenizer)
    # 語の途中(一体の語の内部)では、一致の開始・終了をしないための境界判定
    is_boundary_before = [True] + [
        not isJoinedToPrevious(tokens[k - 1][2], tokens[k][2])
        for k in range(1, len(tokens))
    ]
    result = []
    i = 0
    while i < len(tokens):
        # 語の境界から始まり、語の境界で終わる範囲のうち、最も長く一致するものを探す(長い読みを優先)
        matched_end = None
        matched_word = None
        joined = ""
        if is_boundary_before[i]:
            for j in range(i, len(tokens)):
                joined += tokens[j][1]
                if len(joined) > max_len:
                    break
                is_word_end = j + 1 == len(tokens) or is_boundary_before[j + 1]
                if is_word_end and joined in word_dict:
                    matched_end = j + 1
                    matched_word = word_dict[joined]
        if matched_end is not None:
            result.append(matched_word)
            i = matched_end
        else:
            result.append(tokens[i][0])
            i += 1
    return "".join(result)


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
