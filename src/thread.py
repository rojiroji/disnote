import sys
import time
import threading
from concurrent.futures import (ThreadPoolExecutor, wait)

lock = threading.Lock()

REC_KEY_GOOGLE= 'GOOGLE'
REC_KEY_WITAI = 'WITAI'
REC_KEY_WHISPER='WHISPER'
REC_KEYS=[REC_KEY_GOOGLE, REC_KEY_WITAI, REC_KEY_WHISPER]

ready_recognize = dict() # 音声認識対象ファイルのキュー
ready_convert = dict()   # 音声認識完了ファイルのキュー

for key in REC_KEYS:
	ready_recognize[key] = list()
	ready_convert[key] = list()

# 音声認識のキューに積む
def pushReadyRecognizeList(input_file):
	global lock
	global ready_recognize
	with lock:
		for key in REC_KEYS:
			ready_recognize[key].append(input_file)

# 音声認識対象のキューから取得（空の場合はNoneを返す）
def popReadyRecognizeList(key):
	global lock
	global ready_recognize
	with lock:
		if len(ready_recognize[key]) == 0:
			return None
		return ready_recognize[key].pop(0)

# Google音声認識のキューから取得（空の場合はNoneを返す）
def popReadyRecognizeListGoogle():
	return popReadyRecognizeList(REC_KEY_GOOGLE)

# wit.ai音声認識のキューから取得（空の場合はNoneを返す）
def popReadyRecognizeListWitAI():
	return popReadyRecognizeList(REC_KEY_WITAI)

# whisper音声認識のキューから取得（空の場合はNoneを返す）
def popReadyRecognizeListWhisper():
	return popReadyRecognizeList(REC_KEY_WHISPER)

# 音声認識完了のキューに積む
def pushReadyConvertList(key,input_file):
	global lock
	global ready_convert
	with lock:
		ready_convert[key].append(input_file)

# Google音声認識が完了したキューに積む
def pushReadyConvertListGoogle(input_file):
	pushReadyConvertList(REC_KEY_GOOGLE,input_file)

# wit.ai音声認識が完了したキューに積む
def pushReadyConvertListWitAI(input_file):
	pushReadyConvertList(REC_KEY_WITAI,input_file)

# whisper音声認識が完了したキューに積む
def pushReadyConvertListWhisper(input_file):
	pushReadyConvertList(REC_KEY_WHISPER,input_file)


# 音声認識が完了した要素を返す。pop_andがTrueなら、すべての音声認識が完了している場合のみ（該当の要素がない場合はNoneを返す）
def popReadyConvertList(pop_and):
	global lock
	global ready_convert
	with lock:
		if pop_and: # 音声認識処理すべてが完了した音声を返す
			pop_elem = set(ready_convert[REC_KEY_GOOGLE])
			for key in REC_KEYS:
				pop_elem &= set(ready_convert[key])

		else: # 音声認識処理のうちどれかが完了した音声を返す
			pop_elem = set(ready_convert[REC_KEY_GOOGLE])
			for key in REC_KEYS:
				pop_elem |= set(ready_convert[key])

		if len(pop_elem) == 0:
			return None
		
		# 音声を返す＆リストから消す
		ret = pop_elem.pop()
		for key in REC_KEYS:
			try:
				ready_convert[key].remove(ret)
			except ValueError:
				pass

			
		return ret
