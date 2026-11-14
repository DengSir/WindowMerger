# -*- coding: utf-8 -*-
"""snap_capture_test S1_ALIGN_R MISMATCH 排查探针（非常驻回归）：
复现 efb_align 流程并逐轮打印 EFB 差值，定位靶窗 B 右半对齐不收敛的失败模式。
用法: uv run tools/diag/snap_align_probe.py
标记（英文）：ALIGN_TRACE / DONE
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402

SWP_FLAGS = wm.SWP_NOZORDER | wm.SWP_NOACTIVATE


def efb_align_trace(h: int, target: tuple[int, int, int, int], tag: str) -> None:
    print(f"ALIGN_TRACE {tag} target={target}")
    for i in range(5):
        e = wm.ext_frame_bounds(h)
        if e is None:
            print(f"  iter{i} EFB_NONE")
            return
        dx, dy = target[0] - e.Left, target[1] - e.Top
        dw, dh = target[2] - e.Right, target[3] - e.Bottom
        print(f"  iter{i} efb=({e.Left},{e.Top},{e.Right},{e.Bottom}) "
              f"d=({dx},{dy},{dw},{dh})")
        if max(abs(dx), abs(dy), abs(dw), abs(dh)) <= 1:
            print(f"  converged")
            return
        r = wm.get_window_rect(h)
        wm.set_window_pos(h, None, r.Left + dx, r.Top + dy,
                          r.width + dw, r.height + dh, SWP_FLAGS)
        time.sleep(0.15)  # 探针版给 Tk 消化时间（测试原版无 sleep）
    e = wm.ext_frame_bounds(h)
    print(f"  final efb=({e.Left},{e.Top},{e.Right},{e.Bottom}) "
          f"rect={wm.get_window_rect(h).as_tuple() if wm.get_window_rect(h) else None}")


def kill_title_owners(*titles: str) -> None:
    for t in titles:
        h = wm.find_window_by_title(t)
        if h:
            wm.force_kill_pid(wm.pid_of(h))


def main() -> int:
    kill_title_owners("WM_SNAP_A", "WM_SNAP_B")
    time.sleep(0.5)
    wa = wm.pick_test_monitor().rcWork
    print(f"test work area = ({wa.Left},{wa.Top})-({wa.Right},{wa.Bottom})")
    pa = subprocess.Popen([sys.executable, "tools/targets/snap_target.py", "WM_SNAP_A"], env=wm.host_env())
    pb = subprocess.Popen([sys.executable, "tools/targets/snap_target.py", "WM_SNAP_B"], env=wm.host_env())
    time.sleep(2.0)
    ha = wm.find_window_by_title("WM_SNAP_A")
    hb = wm.find_window_by_title("WM_SNAP_B")
    if not ha or not hb:
        print(f"NO_TARGETS a={ha} b={hb}")
        pa.kill(); pb.kill()
        return 1
    time.sleep(0.3)  # tkinter 首帧布局稳定（与测试同款）
    mid_x = (wa.Left + wa.Right) // 2
    efb_align_trace(ha, (wa.Left, wa.Top, mid_x, wa.Bottom), "A_LEFT_HALF")
    efb_align_trace(hb, (mid_x, wa.Top, wa.Right, wa.Bottom), "B_RIGHT_HALF")
    kill_title_owners("WM_SNAP_A", "WM_SNAP_B")
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
