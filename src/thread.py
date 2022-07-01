import sys
import time
import threading
from concurrent.futures import (ThreadPoolExecutor, wait)

lock = threading.Lock()
ready_recognize_list_google = list()
ready_recognize_list_witai = list()
ready_convert_list_google = list()
ready_convert_list_witai = list()

# 音声認識のキューに積む
def pushReadyRecognizeList(input_file):
	global lock
	global ready_recognize_list_google
	global ready_recognize_list_witai
	with lock:
		ready_recognize_list_google.append(input_file)
		ready_recognize_list_witai.append(input_file)

# Google音声認識のキューから取得（空の場合はNoneを返す）
def popReadyRecognizeListGoogle():
	global lock
	global ready_recognize_list_google
	with lock:
		if len(ready_recognize_list_google) == 0:
			return None
		return ready_recognize_list_google.pop(0)

# wit.ai音声認識のキューから取得（空の場合はNoneを返す）
def popReadyRecognizeListWitAI():
	global lock
	global ready_recognize_list_witai
	with lock:
		if len(ready_recognize_list_witai) == 0:
			return None
		return ready_recognize_list_witai.pop(0)

# Google音声認識が完了したキューに積む
def pushReadyConvertListGoogle(input_file):
	global lock
	global ready_convert_list_google
	with lock:
		ready_convert_list_google.append(input_file)

# wit.ai音声認識が完了したキューに積む
def pushReadyConvertListWitAI(input_file):
	global lock
	global ready_convert_list_witai
	with lock:
		ready_convert_list_witai.append(input_file)

# 音声認識が完了した要素を返す。pop_andがTrueなら、すべての音声認識が完了している場合のみ（該当の要素がない場合はNoneを返す）
def popReadyConvertList(pop_and):
	global lock
	global ready_convert_list_google
	global ready_convert_list_witai
	with lock:
		if pop_and:
			pop_elem = set(ready_convert_list_google) & set(ready_convert_list_witai) # 共通の要素
		else:
			pop_elem = set(ready_convert_list_google) | set(ready_convert_list_witai) # どちらかにはいっていればよい

		if len(pop_elem) == 0:
			return None
		
		ret = pop_elem.pop()
		try:
			ready_convert_list_google.remove(ret)
		except ValueError:
			pass

		try:
			ready_convert_list_witai.remove(ret)
		except ValueError:
			pass
			
		return ret
