"""跟隨滑鼠游標的浮動狀態提示視窗。

使用 PIL 渲染圓角藥丸 + Win32 UpdateLayeredWindow 逐像素透明。
錄音狀態有正弦脈動動畫。在獨立 Win32 訊息迴圈執行緒執行。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── Win32 常數 ──────────────────────────────────────────────────────────────
WS_POPUP         = 0x80000000
WS_EX_TOPMOST    = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED    = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE          = 0
SW_SHOW          = 5
WM_DESTROY       = 0x0002
WM_TIMER         = 0x0113
WM_USER          = 0x0400
WM_APP_SHOW      = WM_USER + 1
WM_APP_HIDE      = WM_USER + 2
WM_APP_QUIT      = WM_USER + 3
ULW_ALPHA        = 0x00000002
AC_SRC_OVER      = 0x00
AC_SRC_ALPHA     = 0x01
DIB_RGB_COLORS   = 0
BI_RGB           = 0
SWP_NOSIZE       = 0x0001
SWP_NOMOVE       = 0x0002
SWP_NOACTIVATE   = 0x0010
SWP_SHOWWINDOW   = 0x0040
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
user32.GetCursorPos.argtypes   = [ctypes.POINTER(wt.POINT)]

# ── Win32 結構 ───────────────────────────────────────────────────────────────
class _BIH(ctypes.Structure):
    _fields_ = [
        ("biSize",wt.DWORD),("biWidth",ctypes.c_long),("biHeight",ctypes.c_long),
        ("biPlanes",wt.WORD),("biBitCount",wt.WORD),("biCompression",wt.DWORD),
        ("biSizeImage",wt.DWORD),("biXPelsPerMeter",ctypes.c_long),
        ("biYPelsPerMeter",ctypes.c_long),("biClrUsed",wt.DWORD),("biClrImportant",wt.DWORD),
    ]

class _BI(ctypes.Structure):
    _fields_ = [("bmiHeader", _BIH), ("bmiColors", wt.DWORD * 3)]

class _BF(ctypes.Structure):
    _fields_ = [
        ("BlendOp",ctypes.c_byte),("BlendFlags",ctypes.c_byte),
        ("SourceConstantAlpha",ctypes.c_byte),("AlphaFormat",ctypes.c_byte),
    ]

# ── 視覺設計 ──────────────────────────────────────────────────────────────────
_W, _H  = 160, 42
_RADIUS = 21          # 完整藥丸
_BG     = (18, 18, 20, 230)

_STATES: dict[str, tuple[str, tuple[int,int,int], bool]] = {
    "recording":    ("錄音中", (255, 69,  58), True),
    "transcribing": ("辨識中", (255, 159, 10), False),
}

_DOT_MIN  = 5
_DOT_MAX  = 8
_DOT_BASE = 7
_DOT_CX   = 22        # 圓點中心 x（留足最大半徑空間）
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
    label, dot_rgb, do_pulse = _STATES[state]
    img  = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, _W - 1, _H - 1], radius=_RADIUS, fill=_BG)

    cy = _H // 2
    r  = int(_DOT_MIN + (_DOT_MAX - _DOT_MIN) * pulse) if do_pulse else _DOT_BASE
    glow_r = r + 5
    glow_a = 40 + int(35 * pulse) if do_pulse else 50
    draw.ellipse(
        [_DOT_CX - glow_r, cy - glow_r, _DOT_CX + glow_r, cy + glow_r],
        fill=(*dot_rgb, glow_a),
    )
    draw.ellipse(
        [_DOT_CX - r, cy - r, _DOT_CX + r, cy + r],
        fill=(*dot_rgb, 255),
    )

    font = _get_font()
    tx   = _DOT_CX + _DOT_MAX + 10
    bbox = draw.textbbox((0, 0), label, font=font)
    ty   = (_H - (bbox[3] - bbox[1])) // 2 - 1
    draw.text((tx, ty), label, font=font, fill=(255, 255, 255, 235))

    return img

# ── PIL RGBA → pre-multiplied BGRA HBITMAP（numpy 加速）───────────────────────
def _to_hbitmap(img: Image.Image) -> int:
    w, h = img.size
    arr  = np.array(img, dtype=np.uint16)   # uint16 防乘法溢位
    a    = arr[:, :, 3:4]
    bgra = np.empty((h, w, 4), dtype=np.uint8)
    bgra[:, :, 0] = (arr[:, :, 2] * a[:, :, 0] // 255).astype(np.uint8)  # B
    bgra[:, :, 1] = (arr[:, :, 1] * a[:, :, 0] // 255).astype(np.uint8)  # G
    bgra[:, :, 2] = (arr[:, :, 0] * a[:, :, 0] // 255).astype(np.uint8)  # R
    bgra[:, :, 3] = arr[:, :, 3].astype(np.uint8)                         # A
    buf = bgra.tobytes()

    bmi = _BI()
    bmi.bmiHeader.biSize      = ctypes.sizeof(_BIH)
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
    if not hbm:
        raise RuntimeError("CreateDIBSection 失敗")
    ctypes.memmove(pbits, buf, len(buf))
    return hbm

# ── StatusOverlay ─────────────────────────────────────────────────────────────
class StatusOverlay:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._ready   = threading.Event()
        self._hwnd    = 0
        self._visible = False
        self._state   = "recording"
        self._tick    = 0

    # ── 公開 API ─────────────────────────────────────────────────────────────

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

    # ── Win32 訊息迴圈 ───────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            self._message_loop()
        except Exception as e:
            print(f"[overlay] 執行緒錯誤: {e}")
            self._ready.set()

    def _message_loop(self) -> None:
        hinstance  = kernel32.GetModuleHandleW(None)
        class_name = "NoTypeOverlayV3"

        class _WC(ctypes.Structure):
            _fields_ = [
                ("style",wt.UINT),("lpfnWndProc",_WNDPROC),("cbClsExtra",ctypes.c_int),
                ("cbWndExtra",ctypes.c_int),("hInstance",wt.HINSTANCE),("hIcon",wt.HICON),
                ("hCursor",wt.HANDLE),("hbrBackground",wt.HBRUSH),
                ("lpszMenuName",wt.LPCWSTR),("lpszClassName",wt.LPCWSTR),
            ]

        def wnd_proc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_APP_SHOW:
                    self._on_show(hwnd)
                    return 0
                elif msg == WM_APP_HIDE:
                    self._on_hide(hwnd)
                    return 0
                elif msg == WM_APP_QUIT:
                    user32.DestroyWindow(hwnd)
                    return 0
                elif msg == WM_TIMER:
                    if wparam == TIMER_PULSE and self._visible:
                        self._tick = (self._tick + 1) % 40
                        self._repaint(hwnd)
                    elif wparam == TIMER_FOLLOW and self._visible:
                        self._follow(hwnd)
                    return 0
                elif msg == WM_DESTROY:
                    user32.KillTimer(hwnd, TIMER_PULSE)
                    user32.KillTimer(hwnd, TIMER_FOLLOW)
                    user32.PostQuitMessage(0)
                    return 0
            except Exception as e:
                print(f"[overlay] wnd_proc error msg={msg}: {e}")
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc = _WNDPROC(wnd_proc)
        wc = _WC()
        wc.lpfnWndProc   = proc
        wc.hInstance     = hinstance
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
            class_name, "", WS_POPUP,
            100, 100, _W, _H,
            None, None, hinstance, None,
        )
        if not hwnd:
            print(f"[overlay] CreateWindowExW 失敗: {kernel32.GetLastError()}")
            self._ready.set()
            return

        self._hwnd = hwnd
        self._ready.set()

        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ── 訊息處理 ─────────────────────────────────────────────────────────────

    def _cursor_xy(self) -> tuple[int, int]:
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x, y = pt.x + 18, pt.y + 18
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        if x + _W > sw: x = sw - _W - 8
        if y + _H > sh: y = sh - _H - 8
        return x, y

    def _ulw(self, hwnd: int, pulse: float, x: Optional[int], y: Optional[int]) -> None:
        """UpdateLayeredWindow。x/y=None 表示不移動。"""
        img = _render(self._state, pulse)
        hbm = _to_hbitmap(img)

        hdc_s = user32.GetDC(None)
        hdc_m = gdi32.CreateCompatibleDC(hdc_s)
        old   = gdi32.SelectObject(hdc_m, hbm)

        pt_src = wt.POINT(); pt_src.x = 0; pt_src.y = 0
        size   = wt.SIZE();  size.cx  = _W; size.cy  = _H
        bf     = _BF(); bf.BlendOp = AC_SRC_OVER; bf.SourceConstantAlpha = 255; bf.AlphaFormat = AC_SRC_ALPHA

        if x is not None:
            pt_dst = wt.POINT(); pt_dst.x = x; pt_dst.y = y
            ret = user32.UpdateLayeredWindow(
                hwnd, hdc_s, ctypes.byref(pt_dst), ctypes.byref(size),
                hdc_m, ctypes.byref(pt_src), 0, ctypes.byref(bf), ULW_ALPHA,
            )
        else:
            ret = user32.UpdateLayeredWindow(
                hwnd, hdc_s, None, ctypes.byref(size),
                hdc_m, ctypes.byref(pt_src), 0, ctypes.byref(bf), ULW_ALPHA,
            )
        if not ret:
            print(f"[overlay] UpdateLayeredWindow failed: {kernel32.GetLastError()}")

        gdi32.SelectObject(hdc_m, old)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_m)
        user32.ReleaseDC(None, hdc_s)

    def _on_show(self, hwnd: int) -> None:
        self._tick = 0
        x, y = self._cursor_xy()
        self._ulw(hwnd, 0.0, x, y)        # 渲染 + 定位
        user32.ShowWindow(hwnd, SW_SHOW)   # 確保可見
        self._visible = True
        user32.SetTimer(hwnd, TIMER_PULSE,  50, None)   # 50ms 脈動
        user32.SetTimer(hwnd, TIMER_FOLLOW, 80, None)   # 80ms 跟游標

    def _on_hide(self, hwnd: int) -> None:
        user32.KillTimer(hwnd, TIMER_PULSE)
        user32.KillTimer(hwnd, TIMER_FOLLOW)
        user32.ShowWindow(hwnd, SW_HIDE)
        self._visible = False

    def _repaint(self, hwnd: int) -> None:
        pulse = (math.sin(self._tick / 40 * 2 * math.pi) + 1) / 2
        self._ulw(hwnd, pulse, None, None)   # 只重繪，不移動

    def _follow(self, hwnd: int) -> None:
        x, y = self._cursor_xy()
        # SetWindowPos 移動即可，不需重繪
        user32.SetWindowPos(
            hwnd, ctypes.c_void_p(-1),   # HWND_TOPMOST
            x, y, 0, 0,
            SWP_NOSIZE | SWP_NOACTIVATE,
        )
