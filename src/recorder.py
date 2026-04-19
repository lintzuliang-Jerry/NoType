"""音訊錄製。

用 sounddevice.InputStream 非同步錄音。
callback 僅寫入 buffer,stop() 才組合出 numpy array。
"""
from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd


SAMPLE_RATE = 16000  # Whisper 需要 16kHz
CHANNELS = 1
MIN_DURATION_SEC = 0.3


class Recorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass
        with self._lock:
            if self._recording:
                self._chunks.append(indata.copy())

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._chunks = []
            self._recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as e:
            with self._lock:
                self._recording = False
            print(f"[recorder] 無法開啟麥克風: {e}")
            self._stream = None

    def stop(self) -> np.ndarray | None:
        with self._lock:
            if not self._recording:
                return None
            self._recording = False

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as e:
            print(f"[recorder] 關閉串流時發生錯誤: {e}")
        finally:
            self._stream = None

        with self._lock:
            chunks = self._chunks
            self._chunks = []

        if not chunks:
            return None

        audio = np.concatenate(chunks, axis=0).flatten().astype(np.float32)
        duration = len(audio) / self.sample_rate
        if duration < MIN_DURATION_SEC:
            print(f"[recorder] 音訊太短 ({duration:.2f}s),略過")
            return None
        return audio
