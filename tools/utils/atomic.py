# -*- coding: utf-8 -*-
"""置顶+截图+自动还原置顶（排查遮挡）。原 Atomic.ps1。
用法: py tools\\utils\\atomic.py <shot.png>
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: atomic.py <shot.png>")
        return 1
    shot_path = sys.argv[1]

    hosts = wm.host_hwnds()
    if not hosts:
        print("NO_WINDOW")
        return 1
    h = hosts[0]

    wm.set_topmost(h, True)
    wm.set_foreground_window(h)
    time.sleep(0.5)

    topmost = wm.is_topmost(h)
    fg = wm.get_foreground_window() == h
    r = wm.get_window_rect(h)
    print(f"TOPMOST={topmost} FOREGROUND={fg} RECT=({r.Left},{r.Top},{r.Right},{r.Bottom})")

    # 顶条
    h1 = wm.window_from_point(r.Left + 60, r.Top + 14)
    print(f"HIT_TOPBAR=0x{h1:X} IS_HOST={h1 == h}")

    # 中央格子（透明 = 点击穿透，应非宿主）
    h2 = wm.window_from_point((r.Left + r.Right) // 2, (r.Top + r.Bottom) // 2)
    print(f"HIT_CENTER=0x{h2:X} IS_HOST={h2 == h} (expect False = click-through)")

    # 左边框
    h3 = wm.window_from_point(r.Left + 1, (r.Top + r.Bottom) // 2)
    print(f"HIT_LEFTBORDER=0x{h3:X} IS_HOST={h3 == h}")

    img = wm.capture_screen(r.Left, r.Top, r.width, r.height)
    img.save(shot_path, "PNG")

    # 截完立即还原普通层级，不污染用户正在跑的实例
    wm.set_topmost(h, False)
    print(f"SHOT_OK {shot_path} (topmost restored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
