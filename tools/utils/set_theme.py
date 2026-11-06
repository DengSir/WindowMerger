# -*- coding: utf-8 -*-
"""改 config.json 主题（Auto/Dark/Light）。原 SetTheme.ps1。
用法: uv run tools/\utils\\set_theme.py [Mode]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "Auto"
    cfg = wm.load_config()
    cfg["Theme"] = mode
    wm.save_config(cfg)
    print(f"THEME_SET={mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
