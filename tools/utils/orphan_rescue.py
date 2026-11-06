# -*- coding: utf-8 -*-
"""孤儿扫描/救援：扫描全部 WS_EX_TOOLWINDOW 顶层窗口（孤儿特征）；
--rescue 按进程摘样式 + 显示 + 拉回屏幕外 -32000 的窗口。原 OrphanRescue.ps1。
用法: py tools\\utils\\orphan_rescue.py [--rescue] [--proc-name xxx]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescue", action="store_true")
    ap.add_argument("--proc-name", default="")
    a = ap.parse_args()

    wa = wm.primary_work_area()
    screen_w, screen_h = wa.Right, wa.Bottom

    found = 0
    cascade = 0
    for i, h in enumerate(wm.z_walk()):
        if i >= 600:
            break
        ex = wm.get_ex_style(h)
        if (ex & wm.WS_EX_TOOLWINDOW) == 0:
            continue
        pid = wm.pid_of(h)
        pn = wm.proc_name_of(h)
        if a.proc_name and pn.lower() != a.proc_name.lower():
            continue
        found += 1
        cls = wm.get_class_name(h, 48)
        title = wm.get_text(h, 64)
        r = wm.get_window_rect(h)
        vis = wm.is_window_visible(h)
        off = r.Left <= -30000 or r.Top <= -30000
        print(f"hwnd=0x{h:X} proc={pn} pid={pid} vis={vis} offscreen={off} "
              f"rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) class={cls} title=[{title}]")
        if a.rescue:
            if not vis:
                print("  SKIP rescue: hidden helper window (never ours)")
            else:
                wm.set_window_long(h, wm.GWL_EXSTYLE, ex & ~wm.WS_EX_TOOLWINDOW)
                wm.show_window(h, wm.SW_SHOWNA)
                if off:
                    x = 60 + (cascade % 5) * 40
                    y = 60 + (cascade % 5) * 40
                    cascade += 1
                    w = min(1200, screen_w - 120)
                    hh = min(800, screen_h - 120)
                    wm.set_window_pos(h, None, x, y, w, hh, wm.SWP_NOZORDER)
                    print(f"  RESCUED: style stripped, shown, moved to ({x},{y}) {w}x{hh}")
                else:
                    print("  RESCUED: style stripped, shown")
    if found == 0:
        print("NO_TOOLWINDOW_WINDOWS")
    print("ORPHAN_SCAN_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
