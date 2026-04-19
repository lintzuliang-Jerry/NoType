"""轉錄歷史,存成 JSON Lines 格式。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class History:
    def __init__(self, path: Path, enabled: bool = True):
        self.path = path
        self.enabled = enabled

    def append(self, text: str, duration_seconds: float, model: str) -> None:
        if not self.enabled or not text:
            return
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": round(duration_seconds, 2),
            "text": text,
            "model": model,
        }
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[history] 寫入失敗: {e}")
