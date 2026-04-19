"""系統匣圖示(pystray)。

pystray.Icon.run() 阻塞主執行緒,所以 main.py 把它放在主執行緒。
狀態更新透過 set_status() 更新圖示標題與選單文字。
"""
from __future__ import annotations

import threading
from typing import Callable

try:
    import pystray
    from PIL import Image, ImageDraw
    _PYSTRAY_AVAILABLE = True
except ImportError:
    _PYSTRAY_AVAILABLE = False


def _make_icon(color: str = "#4A90D9") -> "Image.Image":
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 麥克風身體
    mx, body_w, body_h = size // 2, 20, 28
    draw.rounded_rectangle(
        [mx - body_w // 2, 4, mx + body_w // 2, 4 + body_h],
        radius=10,
        fill=color,
    )
    # 支架弧形(用橢圓弧模擬)
    draw.arc([mx - 16, 20, mx + 16, 48], start=0, end=180, fill=color, width=4)
    # 底部垂直桿
    draw.line([mx, 44, mx, 56], fill=color, width=4)
    # 底座
    draw.line([mx - 10, 56, mx + 10, 56], fill=color, width=4)
    return img


class TrayIcon:
    def __init__(
        self,
        on_toggle: Callable[[bool], None],
        on_open_folder: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        if not _PYSTRAY_AVAILABLE:
            raise RuntimeError("pystray / Pillow 未安裝,無法啟動系統匣")

        self._on_toggle = on_toggle
        self._on_open_folder = on_open_folder
        self._on_quit = on_quit
        self._enabled = True
        self._status = "就緒"
        self._icon: "pystray.Icon | None" = None

    def _build_menu(self) -> "pystray.Menu":
        toggle_label = "停用聽寫" if self._enabled else "啟用聽寫"
        return pystray.Menu(
            pystray.MenuItem(f"狀態: {self._status}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(toggle_label, self._handle_toggle),
            pystray.MenuItem("打開設定資料夾", self._handle_open_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("離開", self._handle_quit),
        )

    def _handle_toggle(self, icon, item) -> None:
        self._enabled = not self._enabled
        self._on_toggle(self._enabled)
        self._refresh()

    def _handle_open_folder(self, icon, item) -> None:
        self._on_open_folder()

    def _handle_quit(self, icon, item) -> None:
        self._on_quit()
        if self._icon:
            self._icon.stop()

    def _refresh(self) -> None:
        if self._icon:
            self._icon.menu = self._build_menu()
            color = "#4A90D9" if self._enabled else "#AAAAAA"
            if self._status == "錄音中":
                color = "#E74C3C"
            self._icon.icon = _make_icon(color)

    def set_status(self, status: str) -> None:
        self._status = status
        self._refresh()

    def run(self) -> None:
        icon_img = _make_icon()
        self._icon = pystray.Icon(
            "voice_dictation",
            icon_img,
            "語音聽寫",
            menu=self._build_menu(),
        )
        self._icon.run()  # 阻塞主執行緒直到 icon.stop()
