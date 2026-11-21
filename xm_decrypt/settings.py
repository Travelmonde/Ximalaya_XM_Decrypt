"""持久化设置（TUI 与 CLI 共用）。

存放位置（按优先级）：
  Linux/macOS:  $XDG_CONFIG_HOME/xm-decrypt/settings.json
                或 ~/.config/xm-decrypt/settings.json
  Windows:      %APPDATA%\\xm-decrypt\\settings.json
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

SETTINGS_DIR_NAME = "xm-decrypt"
SETTINGS_FILE_NAME = "settings.json"


def settings_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
    return root / SETTINGS_DIR_NAME / SETTINGS_FILE_NAME


def default_process_count() -> int:
    return max(1, min(os.cpu_count() or 1, 8))


@dataclass
class Settings:
    input_dir: str = ""
    output_dir: str = "output"
    include_subdirs: bool = False
    wav_mode: str = "keep"
    processes: int = 0  # 0 表示跟随 CPU 核心数（上限 8）

    # ---------- 派生值 ----------
    def resolved_input_dir(self) -> str:
        return str(Path(self.input_dir).expanduser()) if self.input_dir.strip() else os.getcwd()

    def resolved_output_dir(self) -> str:
        return str(Path(self.output_dir).expanduser()) if self.output_dir.strip() else "output"

    def effective_processes(self) -> int:
        if self.processes and self.processes > 0:
            return min(self.processes, max(1, os.cpu_count() or 1) * 4)
        return default_process_count()

    # ---------- 读写 ----------
    @classmethod
    def load(cls) -> Settings:
        try:
            raw = json.loads(settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()

        settings = cls()
        if isinstance(raw.get("input_dir"), str):
            settings.input_dir = raw["input_dir"]
        if isinstance(raw.get("output_dir"), str) and raw["output_dir"].strip():
            settings.output_dir = raw["output_dir"]
        if isinstance(raw.get("include_subdirs"), bool):
            settings.include_subdirs = raw["include_subdirs"]
        if raw.get("wav_mode") in ("keep", "alac"):
            settings.wav_mode = raw["wav_mode"]
        if isinstance(raw.get("processes"), int) and raw["processes"] >= 0:
            settings.processes = raw["processes"]
        return settings

    def save(self) -> Path:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(self), ensure_ascii=False, indent=2)
        # 先写临时文件再原子替换，避免中断留下半截 JSON。
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(path)
        return path
