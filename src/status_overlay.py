"""螢幕中下方固定浮動狀態提示視窗。

使用 PIL 渲染圓角藥丸 + Win32 UpdateLayeredWindow 逐像素透明。
錄音狀態：多層脈動光暈。辨識中：音波線 + 旋轉弧線動畫。
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
_W, _H        = 164, 44
_RADIUS       = 22
_BOTTOM_MARGIN = 90

# 背景色（錄音偏暖、辨識偏冷）
_BG_REC  = (20, 14, 18, 238)
_BG_TRX  = (14, 16, 24, 238)
_BORDER  = (255, 255, 255, 34)
_HL_A    = 10       # 頂部高光 alpha

# 錄音：珊瑚紅
_REC_RGB = (255, 75, 75)
_GLOW_CX = 24
# (extra_radius, alpha_at_full_pulse, alpha_at_zero_pulse)
_GLOW_LAYERS = [
    (15, 14,  4),
    (11, 38, 12),
    (7,  80, 40),
    (4, 170, 130),
    (0, 255, 255),   # 實心核心
]
_CORE_R  = 4

# 辨識：天藍
_TRX_RGB = (80, 175, 255)
# 音波條
_WAVE_CXS     = [14, 20, 26, 32, 38]
_WAVE_BAR_W   = 3
_WAVE_MAX_H   = 16
_WAVE_MIN_H   = 4
# 旋轉弧線
_SPIN_CX      = 146
_SPIN_R       = 7
_SPIN_WIDTH   = 2
_SPIN_ARC     = 100

# 分隔線
_SEP_X  = 42
_SEP_Y1 = 11
_SEP_Y2 = 33

# 文字
_TEXT_X  = 50
_FONT_SZ = 15

# 底部光條
_BAR_X1 = 22
_BAR_X2 = 142
_BAR_Y  = 39
_BAR_H  = 2

_STATES: dict[str, tuple[str, tuple[int,int,int]]] = {
    "recording":    ("錄音中", _REC_RGB),
    "transcribing": ("辨識中", _TRX_RGB),
}

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

def _draw_recording_fx(draw: ImageDraw.ImageDraw, pulse: float) -> None:
    """在 fx 透明層上繪製錄音光暈。"""
    cy = _H // 2
    cx = _GLOW_CX
    max_r = cy - 3  # 保證不超出藥丸上下邊界
    for extra_r, a_max, a_min in _GLOW_LAYERS:
        r = min(_CORE_R + int(extra_r * (0.75 + 0.25 * pulse)), max_r)
        a = int(a_min + (a_max - a_min) * pulse)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=(*_REC_RGB, a))
    # 脈動環
    ring_r = min(_CORE_R + 13, max_r)
    ring_a = int(30 + 55 * pulse)
    draw.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
                 outline=(*_REC_RGB, ring_a), width=1)


def _draw_transcribing_fx(draw: ImageDraw.ImageDraw, tick: int) -> None:
    """在 fx 透明層上繪製音波線和旋轉弧線。"""
    cy = _H // 2
    # 音波條
    for i, cx in enumerate(_WAVE_CXS):
        phase = (tick / 30 * 2 * math.pi) - i * (2 * math.pi / len(_WAVE_CXS))
        t = (math.sin(phase) + 1) / 2
        h = int(_WAVE_MIN_H + (_WAVE_MAX_H - _WAVE_MIN_H) * t)
        a = int(120 + 135 * t)
        x0 = cx - _WAVE_BAR_W // 2
        y0 = cy - h // 2
        draw.rounded_rectangle([x0, y0, x0 + _WAVE_BAR_W, y0 + h],
                               radius=1, fill=(*_TRX_RGB, a))
    # 旋轉弧線
    start_angle = (tick * 6) % 360
    bbox = [_SPIN_CX - _SPIN_R, cy - _SPIN_R,
            _SPIN_CX + _SPIN_R, cy + _SPIN_R]
    draw.arc(bbox, start=start_angle, end=start_angle + _SPIN_ARC,
             fill=(*_TRX_RGB, 200), width=_SPIN_WIDTH)
    # 尾跡弧線（較淡）
    trail_start = (start_angle - 60) % 360
    draw.arc(bbox, start=trail_start, end=trail_start + 50,
             fill=(*_TRX_RGB, 60), width=_SPIN_WIDTH)


def _render(state: str, pulse: float = 0.0, tick: int = 0) -> Image.Image:
    label, accent_rgb = _STATES[state]

    # ── 底圖：背景藥丸 + 邊框 ─────────────────────────────────────────────
    img = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bg = _BG_REC if state == "recording" else _BG_TRX
    draw.rounded_rectangle([0, 0, _W - 1, _H - 1], radius=_RADIUS, fill=bg)
    draw.rounded_rectangle([0, 0, _W - 1, _H - 1], radius=_RADIUS,
                           outline=_BORDER, width=1)

    # ── 頂部高光 ──────────────────────────────────────────────────────────
    hl = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle(
        [2, 2, _W - 3, _H // 3], radius=_RADIUS - 2,
        fill=(255, 255, 255, _HL_A),
    )
    img = Image.alpha_composite(img, hl)

    # ── 特效層（光暈 / 音波 / spinner / 分隔線 / 底部光條）────────────────
    fx = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fx)

    # 分隔線
    fd.line([(_SEP_X, _SEP_Y1), (_SEP_X, _SEP_Y2)],
            fill=(255, 255, 255, 22), width=1)

    # 狀態特效
    if state == "recording":
        _draw_recording_fx(fd, pulse)
        bar_a = int(55 + 130 * pulse)
    else:
        _draw_transcribing_fx(fd, tick)
        bar_a = int(55 + 85 * ((math.sin(tick / 36 * 2 * math.pi) + 1) / 2))

    # 底部光條
    fd.rounded_rectangle([_BAR_X1, _BAR_Y, _BAR_X2, _BAR_Y + _BAR_H],
                         radius=1, fill=(*accent_rgb, bar_a))

    img = Image.alpha_composite(img, fx)

    # ── 文字（近不透明，直接繪製）──────────────────────────────────────────
    draw = ImageDraw.Draw(img)
    font = _get_font()
    bbox = draw.textbbox((0, 0), label, font=font)
    ty = (_H - (bbox[3] - bbox[1])) // 2 - 2
    # 文字陰影
    draw.text((_TEXT_X + 1, ty + 1), label, font=font, fill=(0, 0, 0, 90))
    draw.text((_TEXT_X, ty), label, font=font, fill=(255, 255, 255, 240))

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
        class_name = "NoTypeOverlayV5"

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
        user32.SetTimer(hwnd, TIMER_PULSE, 33, None)   # 33ms ≈ 30fps

    def _on_hide(self, hwnd: int) -> None:
        user32.KillTimer(hwnd, TIMER_PULSE)
        user32.ShowWindow(hwnd, SW_HIDE)
        self._visible = False

    def _repaint(self, hwnd: int) -> None:
        # 錄音：正弦脈動；辨識中：tick 傳給音波/spinner 動畫
        pulse = (math.sin(self._tick / 36 * 2 * math.pi) + 1) / 2
        self._ulw(hwnd, pulse, None, None)
