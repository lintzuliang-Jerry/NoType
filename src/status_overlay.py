"""跟隨滑鼠游標的浮動狀態提示視窗。

使用 PIL 繪製圓角藥丸 + Win32 UpdateLayeredWindow 達到逐像素透明、真圓角。
錄音狀態有脈動(pulse)動畫，轉錄狀態靜態顯示。
在獨立執行緒跑 Win32 訊息迴圈，不使用 tkinter，避免與 pystray 衝突。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import threading
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ── Win32 常數 ──────────────────────────────────────────────────────────────
WS_POPUP         = 0x80000000
WS_EX_TOPMOST    = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED    = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE          = 0
WM_DESTROY       = 0x0002
WM_TIMER         = 0x0113
WM_USER          = 0x0400
WM_APP_SHOW      = WM_USER + 1
WM_APP_HIDE      = WM_USER + 2
WM_APP_QUIT      = WM_USER + 3
WM_APP_MOVE      = WM_USER + 4
ULW_ALPHA        = 0x00000002
AC_SRC_OVER      = 0x00
AC_SRC_ALPHA     = 0x01
DIB_RGB_COLORS   = 0
BI_RGB           = 0
SWP_NOACTIVATE   = 0x0010
SWP_SHOWWINDOW   = 0x0040
SWP_NOSIZE       = 0x0001
HWND_TOPMOST     = -1
TIMER_PULSE      = 1
TIMER_FOLLOW     = 2

user32   = ctypes.windll.user32
gdi32    = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t
)
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype  = ctypes.c_ssize_t
user32.UpdateLayeredWindow.restype = wt.BOOL

# ── Win32 結構 ───────────────────────────────────────────────────────────────
class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          wt.DWORD),
        ("biWidth",         ctypes.c_long),
        ("biHeight",        ctypes.c_long),
        ("biPlanes",        wt.WORD),
        ("biBitCount",      wt.WORD),
        ("biCompression",   wt.DWORD),
        ("biSizeImage",     wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed",       wt.DWORD),
        ("biClrImportant",  wt.DWORD),
    ]

class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp",             ctypes.c_byte),
        ("BlendFlags",          ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat",         ctypes.c_byte),
    ]

# ── 視覺設計 ──────────────────────────────────────────────────────────────────
_W, _H   = 168, 42
_RADIUS  = 21        # 完整藥丸
_BG      = (18, 18, 20, 225)   # 深黑，90% 不透明

# (文字, 圓點顏色 RGB, 是否脈動)
_STATES: dict[str, tuple[str, tuple[int,int,int], bool]] = {
    "recording":    ("錄音中", (255,  69,  58), True),
    "transcribing": ("辨識中", (255, 159,  10), False),
}

_DOT_MIN  = 5    # 脈動最小半徑
_DOT_MAX  = 8    # 脈動最大半徑
_DOT_BASE = 7    # 靜態圓點半徑
_PAD_L    = 16   # 左內距（圓點圓心 x）
_FONT_SZ  = 14

# ── 字型 ─────────────────────────────────────────────────────────────────────
_font_cache: Optional[ImageFont.FreeTypeFont] = None

def _get_font() -> ImageFont.FreeTypeFont:
    global _font_cache
    if _font_cache is None:
        for path in [
            r"C:\Windows\Fonts\msjhbd.ttc",
            r"C:\Windows\Fonts\msjh.ttc",
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\segoeui.ttf",
        ]:
            if Path(path).exists():
                try:
                    _font_cache = ImageFont.truetype(path, _FONT_SZ)
                    break
                except Exception:
                    continue
        if _font_cache is None:
            _font_cache = ImageFont.load_default()
    return _font_cache

# ── PIL 渲染 ─────────────────────────────────────────────────────────────────
def _render(state: str, pulse: float = 0.0) -> Image.Image:
    """pulse 0.0~1.0，0=最小，1=最大（只在 recording 使用）"""
    label, dot_rgb, do_pulse = _STATES[state]
    img  = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景藥丸
    draw.rounded_rectangle([0, 0, _W-1, _H-1], radius=_RADIUS, fill=_BG)

    # 圓點
    cx = _PAD_L + _DOT_MAX   # 固定圓點中心 x，留出最大半徑空間
    cy = _H // 2
    if do_pulse:
        r = _DOT_MIN + int((_DOT_MAX - _DOT_MIN) * pulse)
    else:
        r = _DOT_BASE

    # 外層輝光
    glow_a = 45 + int(30 * pulse) if do_pulse else 50
    glow_r = r + 5
    draw.ellipse(
        [cx-glow_r, cy-glow_r, cx+glow_r, cy+glow_r],
        fill=(*dot_rgb, glow_a),
    )
    # 實心圓點
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*dot_rgb, 255))

    # 文字
    font = _get_font()
    tx   = cx + _DOT_MAX + 10
    bbox = draw.textbbox((0, 0), label, font=font)
    th   = bbox[3] - bbox[1]
    ty   = ((_H - th) // 2) - 1
    draw.text((tx, ty), label, font=font, fill=(255, 255, 255, 235))

    return img

# ── PIL → HBITMAP（pre-multiplied alpha，BGR 排列）────────────────────────────
def _to_hbitmap(img: Image.Image) -> int:
    w, h  = img.size
    raw   = img.tobytes("raw", "RGBA")
    buf   = bytearray(w * h * 4)
    for i in range(w * h):
        r, g, b, a = raw[i*4], raw[i*4+1], raw[i*4+2], raw[i*4+3]
        buf[i*4+0] = b * a // 255
        buf[i*4+1] = g * a // 255
        buf[i*4+2] = r * a // 255
        buf[i*4+3] = a

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize      = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth     = w
    bmi.bmiHeader.biHeight    = -h
    bmi.bmiHeader.biPlanes    = 1
    bmi.bmiHeader.biBitCount  = 32
    bmi.bmiHeader.biCompression = BI_RGB

    pbits = ctypes.c_void_p()
    hbm   = gdi32.CreateDIBSection(
        None, ctypes.byref(bmi), DIB_RGB_COLORS,
        ctypes.byref(pbits), None, 0,
    )
    ctypes.memmove(pbits, bytes(buf), len(buf))
    return hbm

# ── StatusOverlay ─────────────────────────────────────────────────────────────
class StatusOverlay:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._ready   = threading.Event()
        self._hwnd    = 0
        self._visible = False
        self._state   = "recording"
        self._tick    = 0   # 脈動計數器

    # ── 公開 API（任何執行緒均可呼叫）───────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def show(self, state: str) -> None:
        if self._hwnd and state in _STATES:
            self._state = state
            user32.PostMessageW(self._hwnd, WM_APP_SHOW, 0, 0)

    def hide(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_APP_HIDE, 0, 0)

    def stop(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_APP_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2.0)

    # ── Win32 訊息迴圈（背景執行緒）─────────────────────────────────────────

    def _run(self) -> None:
        try:
            self._message_loop()
        except Exception as e:
            print(f"[overlay] 錯誤: {e}")
            self._ready.set()

    def _message_loop(self) -> None:
        hinstance  = kernel32.GetModuleHandleW(None)
        class_name = "NoTypeOverlayV2"

        class _WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style",         wt.UINT),
                ("lpfnWndProc",   _WNDPROC),
                ("cbClsExtra",    ctypes.c_int),
                ("cbWndExtra",    ctypes.c_int),
                ("hInstance",     wt.HINSTANCE),
                ("hIcon",         wt.HICON),
                ("hCursor",       wt.HANDLE),
                ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName",  wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR),
            ]

        def wnd_proc(hwnd, msg, wparam, lparam):
            if   msg == WM_APP_SHOW: self._on_show(hwnd)
            elif msg == WM_APP_HIDE: self._on_hide(hwnd)
            elif msg == WM_APP_MOVE: self._on_move(hwnd)
            elif msg == WM_APP_QUIT: user32.DestroyWindow(hwnd)
            elif msg == WM_TIMER:
                if wparam == TIMER_PULSE and self._visible:
                    self._tick = (self._tick + 1) % 40
                    self._paint(hwnd)
                elif wparam == TIMER_FOLLOW and self._visible:
                    self._reposition(hwnd)
            elif msg == WM_DESTROY:
                user32.KillTimer(hwnd, TIMER_PULSE)
                user32.KillTimer(hwnd, TIMER_FOLLOW)
                user32.PostQuitMessage(0)
            else:
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            return 0

        proc = _WNDPROC(wnd_proc)
        wc = _WNDCLASS()
        wc.lpfnWndProc   = proc
        wc.hInstance     = hinstance
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
            class_name, "", WS_POPUP,
            0, 0, _W, _H,
            None, None, hinstance, None,
        )
        if not hwnd:
            self._ready.set()
            return

        self._hwnd = hwnd
        self._ready.set()

        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ── 訊息處理 ─────────────────────────────────────────────────────────────

    def _on_show(self, hwnd: int) -> None:
        self._tick = 0
        self._reposition(hwnd)
        self._paint(hwnd)
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_NOSIZE | 0x0002,  # SWP_NOMOVE
        )
        self._visible = True
        # 脈動計時器 50ms，游標追蹤 80ms
        user32.SetTimer(hwnd, TIMER_PULSE,  50, None)
        user32.SetTimer(hwnd, TIMER_FOLLOW, 80, None)

    def _on_hide(self, hwnd: int) -> None:
        user32.KillTimer(hwnd, TIMER_PULSE)
        user32.KillTimer(hwnd, TIMER_FOLLOW)
        user32.ShowWindow(hwnd, SW_HIDE)
        self._visible = False

    def _on_move(self, hwnd: int) -> None:
        if self._visible:
            self._reposition(hwnd)

    def _paint(self, hwnd: int) -> None:
        # sin wave pulse：0→1→0，週期 = 40 ticks × 50ms = 2s
        pulse = (math.sin(self._tick / 40 * 2 * math.pi) + 1) / 2
        img   = _render(self._state, pulse)
        hbm   = _to_hbitmap(img)

        hdc_screen = user32.GetDC(None)
        hdc_mem    = gdi32.CreateCompatibleDC(hdc_screen)
        old_bm     = gdi32.SelectObject(hdc_mem, hbm)

        pt_src = wt.POINT(); pt_src.x = 0; pt_src.y = 0
        size   = wt.SIZE();  size.cx  = _W; size.cy  = _H

        blend = _BLENDFUNCTION()
        blend.BlendOp             = AC_SRC_OVER
        blend.SourceConstantAlpha = 255
        blend.AlphaFormat         = AC_SRC_ALPHA

        user32.UpdateLayeredWindow(
            hwnd, hdc_screen,
            None, ctypes.byref(size),
            hdc_mem, ctypes.byref(pt_src),
            0, ctypes.byref(blend), ULW_ALPHA,
        )
        gdi32.SelectObject(hdc_mem, old_bm)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

    def _reposition(self, hwnd: int) -> None:
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x, y = pt.x + 18, pt.y + 18
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        if x + _W > sw: x = sw - _W - 8
        if y + _H > sh: y = sh - _H - 8
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, x, y, 0, 0,
            SWP_NOACTIVATE | SWP_NOSIZE,
        )
