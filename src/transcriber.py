"""Whisper 語音辨識 + OpenCC 簡轉繁。"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .config import Config


class Transcriber:
    def __init__(self, cfg: Config, project_root: Path):
        self.cfg = cfg
        self._model = None
        self._opencc = None
        self._load_model(project_root)
        if cfg.output.convert_to_traditional:
            self._load_opencc(cfg.output.opencc_mode)

    def _load_model(self, project_root: Path) -> None:
        from faster_whisper import WhisperModel

        model_dir = project_root / "models"
        model_dir.mkdir(exist_ok=True)

        print(
            f"[transcriber] 載入 Whisper 模型 '{self.cfg.whisper.model_size}'..."
            f"(首次會下載約 500MB,請耐心等候)"
        )
        self._model = WhisperModel(
            self.cfg.whisper.model_size,
            device=self.cfg.whisper.device,
            compute_type=self.cfg.whisper.compute_type,
            download_root=str(model_dir),
        )
        actual_device = getattr(self._model, "device", self.cfg.whisper.device)
        print(f"[transcriber] Whisper 載入完成,裝置={actual_device}")

    def _load_opencc(self, mode: str) -> None:
        try:
            from opencc import OpenCC
            self._opencc = OpenCC(mode)
            print(f"[transcriber] OpenCC 已載入 (mode={mode})")
        except Exception as e:
            print(f"[transcriber] OpenCC 載入失敗,將不轉繁: {e}")
            self._opencc = None

    def transcribe(self, audio: np.ndarray) -> str:
        if self._model is None:
            return ""

        try:
            segments, _info = self._model.transcribe(
                audio,
                language=self.cfg.whisper.language,
                initial_prompt=self.cfg.whisper.initial_prompt or None,
                vad_filter=True,
            )
            text = "".join(seg.text for seg in segments).strip()
        except Exception as e:
            print(f"[transcriber] 轉錄失敗: {e}")
            return ""

        if self._opencc is not None and text:
            try:
                text = self._opencc.convert(text)
            except Exception as e:
                print(f"[transcriber] OpenCC 轉換失敗,回傳原文: {e}")

        return text
