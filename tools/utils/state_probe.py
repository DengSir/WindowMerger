# -*- coding: utf-8 -*-
"""全状态探针：宿主、左右格命中、前台。原 StateProbe.ps1。
用法: py tools\\utils\\state_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hr = wm.get_window_rect(hm)
    print(f"HOST 0x{hm:X} rect=({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")

    avail = hr.Right - hr.Left - 4 - 8
    for name, frac in (("LEFT", 0.3), ("RIGHT", 0.75)):
        h = wm.window_from_point(int(hr.Left + 2 + avail * frac), (hr.Top + hr.Bottom) // 2)
        print(f"{name}_CENTER proc={wm.proc_name_of(h)}")
    fg = wm.get_foreground_window()
    print(f"FG proc={wm.proc_name_of(fg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
