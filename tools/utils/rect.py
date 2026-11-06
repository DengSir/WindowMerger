# -*- coding: utf-8 -*-
"""按 hwnd/标题查窗口矩形。原 Rect.ps1。
用法: py tools\\utils\\rect.py [--hwnd N] [--title 标题]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwnd", type=lambda v: int(v, 0), default=0)
    ap.add_argument("--title", default="")
    a = ap.parse_args()

    h = a.hwnd
    if h == 0 and a.title:
        h = wm.find_window_by_title(a.title)
    if h == 0:
        print("NOT_FOUND")
        return 1
    if not wm.is_window(h):
        print("NOT_WINDOW")
        return 1
    iconic = wm.is_iconic(h)
    r = wm.get_window_rect(h)
    print(f"HWND=0x{h:X} ICONIC={iconic} RECT=({r.Left},{r.Top},{r.Right},{r.Bottom}) "
          f"SIZE={r.width}x{r.height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
