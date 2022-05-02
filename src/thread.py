import sys
import time
import threading
from concurrent.futures import (ThreadPoolExecutor, wait)

lock = threading.Lock()
ready_recognize_list = list()
ready_convert_list = list()

# 音声認識のキューに積む
def pushReadyRecognizeList(input_file):
	global lock
	global ready_recognize_list
	with lock:
		ready_recognize_list.append(input_file)

# 音声認識のキューから取得（空の場合はNoneを返す）
def popReadyRecognizeList():
	global lock
	global ready_recognize_list
	with lock:
		if len(ready_recognize_list) == 0:
			return None
		return ready_recognize_list.pop(0)

# mp3変換のキューに積む
def pushReadyConvertList(input_file):
	global lock
	global ready_convert_list
	with lock:
		ready_convert_list.append(input_file)

# mp3変換のキューから取得（空の場合はNoneを返す）
def popReadyConvertList():
	global lock
	global ready_convert_list
	with lock:
		if len(ready_convert_list) == 0:
			return None
		return ready_convert_list.pop(0)
