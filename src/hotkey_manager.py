"""熱鍵綁定。

約束:callback 必須立刻返回,不能做轉錄等長任務,
否則 keyboard 內部 hook 執行緒會卡住、其他熱鍵會延遲。
"""
from __future__ import annotations

from typing import Callable

import keyboard


DEFAULT_HOTKEY = "right ctrl"


class HotkeyManager:
    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ):
        self.hotkey = hotkey
        self.on_press = on_press
        self.on_release = on_release
        self._toggle_active = False
        self._hooks: list = []

    def bind(self) -> None:
        try:
            self._do_bind(self.hotkey)
        except Exception as e:
            print(f"[hotkey] 綁定 '{self.hotkey}' 失敗: {e}")
            if self.hotkey != DEFAULT_HOTKEY:
                print(f"[hotkey] 退回預設熱鍵 '{DEFAULT_HOTKEY}'")
                self.hotkey = DEFAULT_HOTKEY
                try:
                    self._do_bind(DEFAULT_HOTKEY)
                except Exception as e2:
                    print(f"[hotkey] 預設熱鍵也綁定失敗: {e2}")
                    raise

    def _do_bind(self, key: str) -> None:
        # Caps Lock 特殊處理:阻止大小寫切換的預設行為
        if key.lower() == "caps lock":
            keyboard.block_key("caps lock")
            print("[hotkey] Caps Lock 大小寫切換已停用(聽寫工具使用中)")

        # 用 hook + name 過濾，確保 right ctrl / left ctrl 不互相干擾
        def _handler(event):
            if event.name == key and event.event_type == keyboard.KEY_DOWN:
                self._toggle_safe()

        h = keyboard.hook(_handler, suppress=False)
        self._hooks.append(h)

    def _toggle_safe(self) -> None:
        try:
            if not self._toggle_active:
                self._toggle_active = True
                self.on_press()
            else:
                self._toggle_active = False
                self.on_release()
        except Exception as e:
            print(f"[hotkey] toggle callback error: {e}")

    def unbind(self) -> None:
        # 若曾封鎖 Caps Lock,解除封鎖
        if self.hotkey.lower() == "caps lock":
            try:
                keyboard.unblock_key("caps lock")
            except Exception:
                pass

        for h in self._hooks:
            try:
                keyboard.unhook(h)
            except Exception:
                pass
        self._hooks = []
