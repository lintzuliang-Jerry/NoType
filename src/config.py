"""設定檔讀寫。

預設值依 PROJECT_SPEC.md §config.json 預設值。
第一次啟動若 config.json 不存在,自動建立並寫回。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


DEFAULT_CONFIG: dict = {
    "hotkey": "right ctrl",
    "hotkey_mode": "hold",
    "whisper": {
        "model_size": "medium",
        "language": "zh",
        "device": "auto",
        "compute_type": "int8",
        "initial_prompt": "以下是一段正式的繁體中文。說話者會講完整的句子並使用適當標點符號。",
    },
    "output": {
        "convert_to_traditional": True,
        "opencc_mode": "s2twp",
        "preserve_clipboard": True,
    },
    "history": {
        "enabled": True,
        "file": "history.jsonl",
    },
    "tray": {
        "enabled": True,
    },
}


@dataclass
class WhisperConfig:
    model_size: str = "medium"
    language: str = "zh"
    device: str = "auto"
    compute_type: str = "int8"
    initial_prompt: str = ""


@dataclass
class OutputConfig:
    convert_to_traditional: bool = True
    opencc_mode: str = "s2twp"
    preserve_clipboard: bool = True


@dataclass
class HistoryConfig:
    enabled: bool = True
    file: str = "history.jsonl"


@dataclass
class TrayConfig:
    enabled: bool = True


@dataclass
class Config:
    hotkey: str = "right ctrl"
    hotkey_mode: str = "hold"
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    tray: TrayConfig = field(default_factory=TrayConfig)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        return cls(
            hotkey=d.get("hotkey", "right ctrl"),
            hotkey_mode=d.get("hotkey_mode", "toggle"),
            whisper=WhisperConfig(**{**asdict(WhisperConfig()), **d.get("whisper", {})}),
            output=OutputConfig(**{**asdict(OutputConfig()), **d.get("output", {})}),
            history=HistoryConfig(**{**asdict(HistoryConfig()), **d.get("history", {})}),
            tray=TrayConfig(**{**asdict(TrayConfig()), **d.get("tray", {})}),
        )


def load_config(path: Path) -> Config:
    if not path.exists():
        print(f"[config] 找不到 {path.name},建立預設設定檔")
        path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return Config.from_dict(DEFAULT_CONFIG)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[config] {path.name} 格式錯誤: {e}。使用預設值(不覆寫檔案)")
        return Config.from_dict(DEFAULT_CONFIG)

    return Config.from_dict(raw)
