"""螢幕中下方固定浮動狀態提示視窗。

使用 PIL 渲染圓角藥丸 + Win32 UpdateLayeredWindow 逐像素透明。
錄音狀態：平滑脈動紅點。辨識中：三點序列淡入淡出動畫。
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
_W, _H        = 124, 50
_RADIUS       = 25
_BOTTOM_MARGIN = 80      # 距螢幕底部距離（px）

# 背景：極深近黑，微帶藍調，高不透明度
_BG           = (11, 11, 16, 248)
_BORDER_A     = 28       # 細邊框 alpha（模擬毛玻璃邊緣）
_SHINE_A      = 12       # 頂部高光 alpha

_STATES: dict[str, tuple[str, tuple[int,int,int], bool]] = {
    "recording":    ("錄音中", (255, 55,  50), True),
    "transcribing": ("辨識中", (255, 149,  0), False),
}

_FONT_SZ      = 15
_DOT_CX       = 26       # 錄音點中心 x
_DOT_MIN      = 5
_DOT_MAX      = 8
_DOT_BASE     = 6

# 辨識中三點
_DOTS3_CX     = [15, 26, 37]   # 三點中心 x
_DOT3_R_MIN   = 3
_DOT3_R_MAX   = 5
_TEXT_X       = 51       # 文字起始 x

# ── 字型 ─────────────────────────────────────────────────────────────────────
_font_cache: Optional[ImageFont.FreeTypeFont] = None

def _get_font() -> ImageFont.FreeTypeFont:
    global _font_cache
    if _font_cache is None:
        for path in [
            r"C:\Windows\Fonts\msjhbd.ttc",   # 微軟正黑粗體
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
def _render(state: str, pulse: float = 0.0, tick: int = 0) -> Image.Image:
    label, dot_rgb, do_pulse = _STATES[state]
    img  = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景藥丸
    draw.rounded_rectangle([0, 0, _W - 1, _H - 1], radius=_RADIUS, fill=_BG)

    # 細緻白色邊框，模擬毛玻璃質感
    draw.rounded_rectangle([0, 0, _W - 1, _H - 1], radius=_RADIUS,
                            outline=(255, 255, 255, _BORDER_A), width=1)

    # 頂部微高光（2px 漸層模擬）
    highlight = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.rounded_rectangle([1, 1, _W - 2, _H // 2], radius=_RADIUS - 1,
                          fill=(255, 255, 255, _SHINE_A))
    img = Image.alpha_composite(img, highlight)
    draw = ImageDraw.Draw(img)

    cy = _H // 2

    if do_pulse:
        # 錄音：單點平滑脈動，帶多層光暈
        r = _DOT_MIN + (_DOT_MAX - _DOT_MIN) * pulse
        for layer_r, layer_a in [
            (r + 11, int(18 * pulse)),
            (r + 6,  int(45 * pulse)),
            (r,      255),
        ]:
            lr = int(layer_r)
            cx = _DOT_CX
            draw.ellipse(
                [cx - lr, cy - lr, cx + lr, cy + lr],
                fill=(*dot_rgb, layer_a),
            )
        tx = _TEXT_X
    else:
        # 辨識中：三點序列淡入淡出（相位差 120°）
        for i, cx in enumerate(_DOTS3_CX):
            phase = (tick / 36 * 2 * math.pi) - i * (2 * math.pi / 3)
            t     = (math.sin(phase) + 1) / 2          # 0.0 ~ 1.0
            alpha = int(60 + 195 * t)
            r     = _DOT3_R_MIN + (_DOT3_R_MAX - _DOT3_R_MIN) * t
            ri    = int(r)
            draw.ellipse(
                [cx - ri, cy - ri, cx + ri, cy + ri],
                fill=(*dot_rgb, alpha),
            )
        tx = _TEXT_X

    font = _get_font()
    bbox = draw.textbbox((0, 0), label, font=font)
    ty   = (_H - (bbox[3] - bbox[1])) // 2 - 3
    draw.text((tx, ty), label, font=font, fill=(255, 255, 255, 230))

    return img

# ── PIL RGBA → pre-multiplied BGRA HBITMAP（numpy 加速）───────────────────────
def _to_hbitmap(img: Image.Image) -> int:
    w, h = img.size
    arr  = np.array(img, dtype=np.uint16)
    a    = arr[:, :, 3:4]
    bgra = np.empty((h, w, 4), dtype=np.uint8)
    bgra[:, :, 0] = (arr[:, :, 2] * a[:, :, 0] // 255).astype(np.uint8)
    bgra[:, :, 1] = (arr[:, :, 1] * a[:, :, 0] // 255).astype(np.uint8)
    bgra[:, :, 2] = (arr[:, :, 0] * a[:, :, 0] // 255).astype(np.uint8)
    bgra[:, :, 3] = arr[:, :, 3].astype(np.uint8)
    buf = bgra.tobytes()

    bmi = _BI()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BIH)
    bmi.bmiHeader.biWidth       = w
    bmi.bmiHeader.biHeight      = -h
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
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

# ── 螢幕中下方位置 ────────────────────────────────────────────────────────────
def _screen_center_bottom() -> tuple[int, int]:
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    x  = (sw - _W) // 2
    y  = sh - _H - _BOTTOM_MARGIN
    return x, y

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
        class_name = "NoTypeOverlayV4"

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
                        self._tick = (self._tick + 1) % 360
                        self._repaint(hwnd)
                    return 0
                elif msg == WM_DESTROY:
                    user32.KillTimer(hwnd, TIMER_PULSE)
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

        x, y = _screen_center_bottom()
        hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
            class_name, "", WS_POPUP,
            x, y, _W, _H,
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

    def _ulw(self, hwnd: int, pulse: float, x: Optional[int], y: Optional[int]) -> None:
        img = _render(self._state, pulse, self._tick)
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
        x, y = _screen_center_bottom()
        self._ulw(hwnd, 0.0, x, y)
        user32.ShowWindow(hwnd, SW_SHOW)
        self._visible = True
        user32.SetTimer(hwnd, TIMER_PULSE, 40, None)   # 40ms ≈ 25fps

    def _on_hide(self, hwnd: int) -> None:
        user32.KillTimer(hwnd, TIMER_PULSE)
        user32.ShowWindow(hwnd, SW_HIDE)
        self._visible = False

    def _repaint(self, hwnd: int) -> None:
        # 錄音：正弦脈動；辨識中：tick 傳給三點動畫
        pulse = (math.sin(self._tick / 36 * 2 * math.pi) + 1) / 2
        self._ulw(hwnd, pulse, None, None)
