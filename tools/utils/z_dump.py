# -*- coding: utf-8 -*-
"""只读 z 序 dump，不动/不杀任何窗口。原 ZDump.ps1。
用法: py tools\\utils\\z_dump.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    hm = wm.host_hwnd()
    fg = wm.get_foreground_window()
    print(f"FG proc={wm.proc_name_of(fg)}")

    if hm:
        hr = wm.get_window_rect(hm)
        print(f"HOST rect=({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")
        avail = hr.Right - hr.Left - 12
        probes = [
            ("TOPBAR", (hr.Left + hr.Right) // 2, hr.Top + 14),
            ("LEFT", int(hr.Left + 2 + avail * 0.35), (hr.Top + hr.Bottom) // 2),
            ("RIGHT", int(hr.Left + 2 + avail * 0.75), (hr.Top + hr.Bottom) // 2),
        ]
        for name, px, py in probes:
            h = wm.window_from_point(px, py)
            print(f"HIT {name:<6} proc={wm.proc_name_of(h)}")

    print("--- z-order top 30 visible windows ---")
    i = 0
    for h in wm.z_walk():
        if i >= 30:
            break
        if wm.is_window_visible(h):
            ex = wm.get_ex_style(h)
            t = wm.get_text(h, 64)
            r = wm.get_window_rect(h)
            topmost = (ex & wm.WS_EX_TOPMOST) != 0
            tool = (ex & wm.WS_EX_TOOLWINDOW) != 0
            mark = " <== HOST" if h == hm else ""
            print(f"Z{i:<2} {wm.proc_name_of(h):<12} topmost={topmost} tool={tool} "
                  f"y={r.Top} [{t}]{mark}")
            i += 1
    print("DUMP_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
