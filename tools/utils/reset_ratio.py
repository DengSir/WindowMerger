# -*- coding: utf-8 -*-
"""分隔比例复位 0.5（改 config.json）。原 ResetRatio.ps1。
用法: py tools\\utils\\reset_ratio.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    cfg = wm.load_config()
    print(f"CURRENT_RATIO={cfg.get('Ratio')}")
    cfg["Ratio"] = 0.5
    wm.save_config(cfg)
    print("RATIO_RESET_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
