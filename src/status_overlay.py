"""跟隨滑鼠游標的浮動狀態提示視窗。

使用 Win32 API (ctypes) 建立無邊框視窗,在獨立執行緒跑訊息迴圈。
避免與 pystray 共用 tkinter 造成的執行緒衝突。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from typing import Optional

# Win32 常數
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SW_SHOW = 5
WM_DESTROY = 0x0002
WM_USER = 0x0400
WM_APP_SHOW = WM_USER + 1
WM_APP_HIDE = WM_USER + 2
WM_APP_QUIT = WM_USER + 3
LWA_ALPHA = 0x00000002
DT_CENTER = 0x00000001
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020

_STATES = {
    "recording": ("🎤 錄音中", 0x003CB4E7),   # BGR: 紅 #E74C3C
    "transcribing": ("⏳ 轉錄中", 0x0022A5E6),  # BGR: 橙 #E6A522
}

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# 64-bit 正確型別宣告
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t


class StatusOverlay:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._hwnd: int = 0
        self._current_state: str = "recording"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def show(self, state: str) -> None:
        if self._hwnd and state in _STATES:
            self._current_state = state
            user32.PostMessageW(self._hwnd, WM_APP_SHOW, 0, 0)

    def hide(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_APP_HIDE, 0, 0)

    def stop(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_APP_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            self._message_loop()
        except Exception as e:
            print(f"[overlay] 執行錯誤: {e}")
            self._ready.set()

    def _message_loop(self) -> None:
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t
        )

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_APP_SHOW:
                self._do_show(hwnd)
                return 0
            elif msg == WM_APP_HIDE:
                user32.ShowWindow(hwnd, SW_HIDE)
                return 0
            elif msg == WM_APP_QUIT:
                user32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc = WNDPROC(wnd_proc)

        hinstance = kernel32.GetModuleHandleW(None)
        class_name = "NoTypeOverlay"

        WNDCLASSW = ctypes.Structure
        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", wt.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR),
            ]

        wc = WNDCLASS()
        wc.lpfnWndProc = proc
        wc.hInstance = hinstance
        wc.hbrBackground = gdi32.CreateSolidBrush(0x003CB4E7)
        wc.lpszClassName = class_name

        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
            class_name, "",
            WS_POPUP,
            0, 0, 180, 36,
            None, None, hinstance, None,
        )
        if not hwnd:
            self._ready.set()
            return

        user32.SetLayeredWindowAttributes(hwnd, 0, 230, LWA_ALPHA)
        self._hwnd = hwnd
        self._ready.set()

        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _do_show(self, hwnd: int) -> None:
        text, color_bgr = _STATES[self._current_state]

        # 更新背景色
        hbr = gdi32.CreateSolidBrush(color_bgr)

        # 取游標位置
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x, y = pt.x + 16, pt.y + 16

        # 取螢幕尺寸防溢出
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        w, h = 180, 36
        if x + w > sw:
            x = sw - w - 4
        if y + h > sh:
            y = sh - h - 4

        user32.SetWindowPos(hwnd, None, x, y, w, h, 0x0040)  # SWP_SHOWWINDOW
        user32.ShowWindow(hwnd, SW_SHOW)

        # 繪製文字
        hdc = user32.GetDC(hwnd)
        rect = wt.RECT()
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, w, h

        # 填背景
        user32.FillRect(hdc, ctypes.byref(rect), hbr)

        # 文字
        gdi32.SetTextColor(hdc, 0x00FFFFFF)
        gdi32.SetBkMode(hdc, 1)  # TRANSPARENT
        hfont = gdi32.CreateFontW(
            18, 0, 0, 0, 700, 0, 0, 0,
            136,  # CHINESEBIG5_CHARSET
            0, 0, 0, 0,
            "Microsoft JhengHei UI"
        )
        old_font = gdi32.SelectObject(hdc, hfont)
        user32.DrawTextW(
            hdc, text, -1, ctypes.byref(rect),
            DT_CENTER | DT_VCENTER | DT_SINGLELINE
        )
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(hfont)
        gdi32.DeleteObject(hbr)
        user32.ReleaseDC(hwnd, hdc)
