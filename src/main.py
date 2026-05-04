"""主程式進入點。

執行緒架構:
  主執行緒       : 若 tray.enabled → pystray.Icon.run()(阻塞)
                   否則           → keyboard.wait('esc')
  worker 執行緒  : 消費 queue,做 Transcriber + TextInjector + History
  keyboard hook  : 只做 Recorder.start/stop,stop 時把任務丟進 queue
  sounddevice cb : 只寫 buffer
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import NamedTuple

import keyboard
import numpy as np

from .config import load_config, Config
from .history import History
from .hotkey_manager import HotkeyManager
from .recorder import Recorder
from .status_overlay import StatusOverlay
from .text_injector import TextInjector
from .transcriber import Transcriber


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


class TranscribeTask(NamedTuple):
    audio: np.ndarray
    started_at: float  # time.monotonic()


def worker_loop(
    q: "queue.Queue[TranscribeTask | None]",
    transcriber: Transcriber,
    injector: TextInjector,
    history: History,
    cfg: Config,
    tray_ref: list,  # tray_ref[0] 存 TrayIcon 或 None,延遲初始化
    overlay: StatusOverlay,
) -> None:
    while True:
        item = q.get()
        if item is None:
            break
        try:
            tray = tray_ref[0] if tray_ref else None
            if tray:
                tray.set_status("轉錄中")
            overlay.show("transcribing")

            print("[main] ⏳ 轉錄中...")
            text = transcriber.transcribe(item.audio)
            duration = time.monotonic() - item.started_at

            if not text:
                print("[main] (空結果,略過)")
            else:
                print(f"[main] ✓ {text}")
                injector.inject(text)
                history.append(
                    text=text,
                    duration_seconds=duration,
                    model=cfg.whisper.model_size,
                )

            if tray:
                tray.set_status("就緒")
            overlay.hide()
        except Exception as e:
            print(f"[main] worker error: {e}")
            tray = tray_ref[0] if tray_ref else None
            if tray:
                tray.set_status("就緒")
            overlay.hide()
        finally:
            q.task_done()


def main() -> int:
    cfg: Config = load_config(CONFIG_PATH)

    try:
        transcriber = Transcriber(cfg, PROJECT_ROOT)
    except Exception as e:
        print(f"[main] 載入 Whisper 失敗,無法繼續: {e}")
        return 1

    recorder = Recorder()
    injector = TextInjector(preserve_clipboard=cfg.output.preserve_clipboard)
    history = History(
        path=PROJECT_ROOT / cfg.history.file,
        enabled=cfg.history.enabled,
    )
    overlay = StatusOverlay()
    overlay.start()

    task_queue: queue.Queue[TranscribeTask | None] = queue.Queue()
    tray_ref: list = [None]
    dictation_enabled = [True]  # 用 list 使 closure 可寫

    worker = threading.Thread(
        target=worker_loop,
        args=(task_queue, transcriber, injector, history, cfg, tray_ref, overlay),
        daemon=True,
    )
    worker.start()

    def on_press() -> None:
        if not dictation_enabled[0]:
            return
        recorder.start()
        print("[main] 🎤 錄音中...")
        tray = tray_ref[0]
        if tray:
            tray.set_status("錄音中")
        overlay.show("recording")

    def on_release() -> None:
        audio = recorder.stop()
        overlay.hide()
        if audio is None:
            return
        task_queue.put(TranscribeTask(audio=audio, started_at=time.monotonic()))

    hotkeys = HotkeyManager(
        hotkey=cfg.hotkey,
        mode=cfg.hotkey_mode,
        on_press=on_press,
        on_release=on_release,
    )
    try:
        hotkeys.bind()
    except Exception as e:
        print(f"[main] 熱鍵無法綁定,程式結束: {e}")
        return 1

    print()
    print(f"[main] 就緒。按 '{hotkeys.hotkey}' 開始錄音,再按一次停止並轉錄。")

    def shutdown() -> None:
        print("[main] 結束中...")
        hotkeys.unbind()
        task_queue.put(None)
        worker.join(timeout=3.0)
        overlay.stop()

    # ---------- 主執行緒:tray 或 keyboard.wait ----------
    if cfg.tray.enabled:
        try:
            from .tray import TrayIcon
        except RuntimeError as e:
            print(f"[main] 系統匣無法啟動({e}),改用終端機模式")
            cfg.tray.enabled = False

    if cfg.tray.enabled:
        def on_toggle(enabled: bool) -> None:
            dictation_enabled[0] = enabled
            state = "啟用" if enabled else "停用"
            print(f"[main] 聽寫已{state}")

        def on_open_folder() -> None:
            os.startfile(str(PROJECT_ROOT))

        tray = TrayIcon(
            on_toggle=on_toggle,
            on_open_folder=on_open_folder,
            on_quit=shutdown,
        )
        tray_ref[0] = tray
        print("[main] 程式常駐於系統匣。右鍵圖示可控制。")
        tray.run()  # 阻塞主執行緒
    else:
        print("[main] 按 Esc 結束程式。")
        try:
            keyboard.wait("esc")
        except KeyboardInterrupt:
            pass
        finally:
            shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
