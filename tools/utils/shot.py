# -*- coding: utf-8 -*-
"""全屏/区域截图存 PNG。原 Shot.ps1。
用法: uv run tools\\utils\\shot.py <out.png> [--x N --y N --w N --h N]（缺省 = 主屏全屏）
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--x", type=int, default=-1)
    ap.add_argument("--y", type=int, default=-1)
    ap.add_argument("--w", type=int, default=-1)
    ap.add_argument("--h", type=int, default=-1)
    a = ap.parse_args()

    x, y, w, h = a.x, a.y, a.w, a.h
    if x < 0:
        # 主屏边界（物理像素，进程已 DPI aware）
        w = wm.get_system_metrics(wm.SM_CXSCREEN)
        h = wm.get_system_metrics(wm.SM_CYSCREEN)
        x, y = 0, 0

    img = wm.capture_screen(x, y, w, h)
    img.save(a.path, "PNG")
    print(f"SHOT_OK {a.path} ({x},{y},{w},{h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
