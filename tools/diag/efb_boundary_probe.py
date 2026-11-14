# -*- coding: utf-8 -*-
"""EFB 跨 DPI 屏界读数探针（非常驻回归）：同一窗口摆三种位置，对比 GetWindowRect
与 DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)：
  P1 完全在 4K 屏内
  P2 左缘跨过 x=0 分界（模拟 snap 左窗：可见缘=0，GetWindowRect 左=-9）
  P3 贴住分界但不出屏（可见缘=0，GetWindowRect 左=0——EFB 应=0）
若 P2/P3 的 EFB 相对 GetWindowRect 的差值与 P1 不一致（被邻屏 DPI 虚拟化/偏移），
即 SnapLayoutDetector 在 150% 屏抓不到布局的根因。
用法: uv run tools/diag/efb_boundary_probe.py
标记（英文）：CASE / DONE
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402

SWP_FLAGS = wm.SWP_NOZORDER | wm.SWP_NOACTIVATE
TARGET = Path(__file__).resolve().parents[1] / "targets" / "snap_target.py"


def kill_title_owners(*titles: str) -> None:
    for t in titles:
        h = wm.find_window_by_title(t)
        if h:
            wm.force_kill_pid(wm.pid_of(h))


def show(tag: str, h: int, rect: tuple[int, int, int, int]) -> None:
    wm.set_window_pos(h, None, *rect, SWP_FLAGS)
    time.sleep(0.4)
    r = wm.get_window_rect(h)
    e = wm.ext_frame_bounds(h)
    print(f"CASE {tag}")
    print(f"  want rect={rect}")
    print(f"  got  rect={r.as_tuple() if r else None}")
    print(f"  efb={e.as_tuple() if e else None}")
    if r and e:
        print(f"  margins L{e.Left - r.Left} T{e.Top - r.Top} "
              f"R{e.Right - r.Right} B{e.Bottom - r.Bottom}")


def main() -> int:
    kill_title_owners("WM_SNAP_A")
    time.sleep(0.5)
    subprocess.Popen([sys.executable, str(TARGET), "WM_SNAP_A", "800x600+100+100"],
                     env=wm.host_env())
    h = 0
    for _ in range(100):
        h = wm.find_window_by_title("WM_SNAP_A")
        if h:
            break
        time.sleep(0.1)
    if not h:
        print("NO_TARGET")
        return 1
    time.sleep(0.5)

    # 4K 主屏工作区 (0,0)-(3840,2088)，分界 x=0（左侧 96DPI 屏）
    show("P1_全在4K屏内", h, (1000, 300, 1800, 900))
    show("P3_可见缘贴分界", h, (0, 300, 800, 900))
    show("P2_跨过分界9px", h, (-9, 300, 791, 900))
    show("P1b_回到屏内", h, (1000, 300, 1800, 900))
    kill_title_owners("WM_SNAP_A")
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
