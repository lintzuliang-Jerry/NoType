"""文字貼到游標位置。

做法:pyperclip 複製 → keyboard.send('ctrl+v')。
使用 keyboard.send 而非 pyautogui,是因為 keyboard 走 SendInput scancode,
在中文 IME 啟用時不會被攔截成字元 v。
"""
from __future__ import annotations

import time

import keyboard
import pyperclip


class TextInjector:
    def __init__(self, preserve_clipboard: bool = True):
        self.preserve_clipboard = preserve_clipboard

    def inject(self, text: str) -> None:
        if not text:
            return

        old_clipboard: str | None = None
        if self.preserve_clipboard:
            try:
                old_clipboard = pyperclip.paste()
            except Exception as e:
                print(f"[injector] 讀取剪貼簿失敗(非文字格式會遺失): {e}")
                old_clipboard = None

        try:
            pyperclip.copy(text)
        except Exception as e:
            print(f"[injector] 寫入剪貼簿失敗: {e}")
            return

        time.sleep(0.05)

        try:
            keyboard.send("ctrl+v")
        except Exception as e:
            print(f"[injector] 模擬 Ctrl+V 失敗: {e}")

        time.sleep(0.10)

        if self.preserve_clipboard and old_clipboard is not None:
            try:
                pyperclip.copy(old_clipboard)
            except Exception as e:
                print(f"[injector] 還原剪貼簿失敗: {e}")
