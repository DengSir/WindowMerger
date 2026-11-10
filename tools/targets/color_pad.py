# -*- coding: utf-8 -*-
"""纯色标记窗（诊断专用）：无边框、无任务栏（overrideredirect），垫在被测窗口后面。
透过被测窗口的透明缝隙能看到它，用于像素级判定"哪里透出了宿主后面的内容"。
用法: uv run tools/targets/color_pad.py --color 255,0,255 --geometry 1200x600+20+40
"""
import argparse
import tkinter as tk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--color", default="255,0,255")
    ap.add_argument("--geometry", required=True, help="WxH+X+Y（物理像素）")
    a = ap.parse_args()
    r, g, b = (int(v) for v in a.color.split(","))
    root = tk.Tk()
    root.title("WM_COLOR_PAD")
    root.overrideredirect(True)
    root.geometry(a.geometry)
    root.configure(bg=f"#{r:02x}{g:02x}{b:02x}")
    root.mainloop()


if __name__ == "__main__":
    main()
