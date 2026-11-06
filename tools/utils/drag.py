# -*- coding: utf-8 -*-
"""注入式拖动。原 Drag.ps1。（AGENTS.md：注入式自动拖动受前台锁/覆盖窗干扰不可靠，回归别走这条）
用法: py tools\\utils\\drag.py <X1> <Y1> <X2> <Y2> [--steps 30] [--delay-ms 20]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("x1", type=int)
    ap.add_argument("y1", type=int)
    ap.add_argument("x2", type=int)
    ap.add_argument("y2", type=int)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--delay-ms", type=int, default=20)
    a = ap.parse_args()

    wm.set_cursor_pos(a.x1, a.y1)
    time.sleep(0.12)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.12)

    for i in range(1, a.steps + 1):
        x = a.x1 + int((a.x2 - a.x1) * i / a.steps)
        y = a.y1 + int((a.y2 - a.y1) * i / a.steps)
        wm.set_cursor_pos(x, y)
        time.sleep(a.delay_ms / 1000)

    time.sleep(0.12)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(0.15)
    print(f"DRAG_DONE ({a.x1},{a.y1})->({a.x2},{a.y2})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
