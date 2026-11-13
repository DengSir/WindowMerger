# -*- coding: utf-8 -*-
"""诊断：内嵌 ico 的帧目录（PNG/DIB 格式判定）——tray 图标解码路径排查用。"""
import struct
import sys
from pathlib import Path

data = Path(__file__).resolve().parents[2].joinpath("assets", "WindowMerger.ico").read_bytes()
count = struct.unpack("<H", data[4:6])[0]
print("entries:", count)
for i in range(count):
    off = 6 + 16 * i
    w, h, cc, r, planes, bc, size, offset = struct.unpack("<BBBBHHII", data[off:off + 16])
    magic = data[offset:offset + 4]
    if magic == b"\x89PNG":
        kind = "PNG"
    elif magic == b"\x28\x00\x00\x00":
        kind = "DIB"
    else:
        kind = magic.hex()
    print(f"  [{i}] {w or 256}x{h or 256} bitcount={bc} bytes={size} fmt={kind}")
