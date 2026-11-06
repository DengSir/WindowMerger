# -*- coding: utf-8 -*-
"""查某点 WindowFromPoint 命中（窗口/类/PID/标题）。原 Hit.ps1。
用法: uv run tools/\utils\\hit.py <X> <Y>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: hit.py <X> <Y>")
        return 1
    x, y = int(sys.argv[1]), int(sys.argv[2])

    h = wm.window_from_point(x, y)
    if h == 0:
        print("WINDOW=0")
        return 0

    r = wm.get_window_rect(h)
    cls = wm.get_class_name(h)
    pid = wm.pid_of(h)
    proc = wm.proc_name_of(h)
    title = wm.get_text(h)
    print(f"HWND=0x{h:X} RECT=({r.Left},{r.Top},{r.Right},{r.Bottom}) "
          f"CLASS={cls} PID={pid} PROC={proc} TITLE={title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
