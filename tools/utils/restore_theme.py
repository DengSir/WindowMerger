# -*- coding: utf-8 -*-
"""恢复用户主题设置为 Auto。原 RestoreTheme.ps1。
用法: uv run tools/\utils\\restore_theme.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("THEME_RESTORED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
