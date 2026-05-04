"""熱鍵綁定。

約束:callback 必須立刻返回,不能做轉錄等長任務,
否則 keyboard 內部 hook 執行緒會卡住、其他熱鍵會延遲。

支援兩種模式:
  hold   – 按住說話,放開停止並轉錄（需處理 KEY_DOWN 重複觸發）
  toggle – 按一下開始,再按一下停止
"""
from __future__ import annotations

from typing import Callable

import keyboard


DEFAULT_HOTKEY = "right ctrl"


class HotkeyManager:
    def __init__(
        self,
        hotkey: str,
        mode: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ):
        self.hotkey = hotkey
        self._mode = mode if mode in ("hold", "toggle") else "hold"
        self.on_press = on_press
        self.on_release = on_release
        self._toggle_active = False
        self._hold_active = False
        self._hooks: list = []
        self._expected_scans: set[int] = set()

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

        # 預先取得 scan code，匹配時優先用 scan code（比 event.name 穩定）
        # keyboard.key_to_scan_codes("right ctrl") 會包含左 ctrl 的 scan code，
        # 需要排除對側按鍵的 scan code 以確保只匹配指定側
        try:
            raw_scans = set(keyboard.key_to_scan_codes(key))
            # 若指定 right/left，排除對側的 scan code
            opposite = None
            key_lower = key.lower()
            if key_lower.startswith("right "):
                opposite = "left " + key_lower[6:]
            elif key_lower.startswith("left "):
                opposite = "right " + key_lower[5:]
            if opposite:
                try:
                    opposite_scans = set(keyboard.key_to_scan_codes(opposite))
                    raw_scans -= opposite_scans
                except (ValueError, KeyError):
                    pass
            self._expected_scans = raw_scans
        except (ValueError, KeyError):
            self._expected_scans = set()
            print(f"[hotkey] 無法取得 '{key}' 的 scan code，將退回 name 匹配")

        def _handler(event):
            # 優先 scan code 匹配，fallback 到 name 匹配
            matched = (
                (self._expected_scans and event.scan_code in self._expected_scans)
                or event.name == key
            )
            if not matched:
                return

            if self._mode == "hold":
                self._handle_hold(event)
            else:
                self._handle_toggle(event)

        h = keyboard.hook(_handler, suppress=False)
        self._hooks.append(h)

    def _handle_hold(self, event) -> None:
        """按住說話,放開停止。忽略 KEY_DOWN 重複觸發。"""
        try:
            if event.event_type == keyboard.KEY_DOWN and not self._hold_active:
                self._hold_active = True
                self.on_press()
            elif event.event_type == keyboard.KEY_UP and self._hold_active:
                self._hold_active = False
                self.on_release()
        except Exception as e:
            print(f"[hotkey] hold callback error: {e}")

    def _handle_toggle(self, event) -> None:
        """按一下開始,再按一下停止。只在 KEY_DOWN 觸發。"""
        if event.event_type != keyboard.KEY_DOWN:
            return
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
