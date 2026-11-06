# -*- coding: utf-8 -*-
"""PNG 区域放大（检字形/像素，最近邻插值）。原 ZoomPng.ps1。
用法: uv run tools/\utils\\zoom_png.py --in <png> --out <png> [--scale 3] [--x 0 --y 0 --w 0 --h 0]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--w", type=int, default=0)
    ap.add_argument("--h", type=int, default=0)
    a = ap.parse_args()

    src = Image.open(a.src)
    w = a.w if a.w > 0 else src.width - a.x
    h = a.h if a.h > 0 else src.height - a.y
    crop = src.crop((a.x, a.y, a.x + w, a.y + h))
    zw, zh = w * a.scale, h * a.scale
    zoom = crop.resize((zw, zh), Image.NEAREST)
    zoom.save(a.dst)
    print(f"ZOOMED {zw}x{zh} -> {a.dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
