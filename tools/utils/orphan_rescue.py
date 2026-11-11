# -*- coding: utf-8 -*-
r"""孤儿扫描/救援：吸附窗口隐藏任务栏已改用 ITaskbarList::DeleteTab（不再有 toolwindow
样式），孤儿特征 = DWMWA_WINDOW_CORNER_PREFERENCE==1（DONOTROUND 直角化，只有吸附流程
会设）；--rescue 对匹配窗口重新收录任务栏 + 圆角还原 + 拉回屏幕外 -32000 的窗口。
原 OrphanRescue.ps1（旧版按 WS_EX_TOOLWINDOW 扫描，DeleteTab 方案下失效）。
用法: uv run tools/utils/orphan_rescue.py [--rescue] [--proc-name xxx]
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
        if wm.corner_pref(h) != 1:
            continue  # 吸附态孤儿特征：圆角仍被直角化（隐藏任务栏的 tab 态无查询接口，一并救）
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
                wm.taskbar_tab(h, True)   # 任务栏/Alt+Tab 重新收录
                wm.set_corner_pref(h, 0)  # 圆角还原 DEFAULT
                if off:
                    x = 60 + (cascade % 5) * 40
                    y = 60 + (cascade % 5) * 40
                    cascade += 1
                    w = min(1200, screen_w - 120)
                    hh = min(800, screen_h - 120)
                    wm.set_window_pos(h, None, x, y, w, hh, wm.SWP_NOZORDER)
                    print(f"  RESCUED: tab re-added, corners restored, moved to ({x},{y}) {w}x{hh}")
                else:
                    print("  RESCUED: tab re-added, corners restored")
    if found == 0:
        print("NO_ORPHAN_CANDIDATES")
    print("ORPHAN_SCAN_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
