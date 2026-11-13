# -*- coding: utf-8 -*-
"""诊断：THIRDS 场景（三窗三等分）对齐后各窗实际 EFB 与检测结果。
S4_THIRDS 假失败（NO_LAYOUT 而非 TOO_MANY:3）定位用。

用法: uv run tools/diag/thirds_align_probe.py
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

TARGET_SCRIPT = Path(__file__).resolve().parents[1] / "targets" / "snap_target.py"
EXE = wm.exe_path()
SWP_FLAGS = 0x0004 | 0x0010


def wait_window(title: str, timeout_ms: int = 8000) -> int:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        h = wm.find_window_by_title(title)
        if h:
            return h
        time.sleep(0.1)
    return 0


def efb_align(h: int, target: tuple[int, int, int, int]) -> bool:
    for _ in range(5):
        e = wm.ext_frame_bounds(h)
        if e is None:
            return False
        dx, dy = target[0] - e.Left, target[1] - e.Top
        dw, dh = target[2] - e.Right, target[3] - e.Bottom
        if max(abs(dx), abs(dy), abs(dw), abs(dh)) <= 1:
            return True
        r = wm.get_window_rect(h)
        if r is None:
            return False
        wm.set_window_pos(h, None, r.Left + dx, r.Top + dy, r.width + dw, r.height + dh, SWP_FLAGS)
    e = wm.ext_frame_bounds(h)
    if e is None:
        return False
    return max(abs(target[0] - e.Left), abs(target[1] - e.Top),
               abs(target[2] - e.Right), abs(target[3] - e.Bottom)) <= 2


def main() -> int:
    import os
    os.environ["WM_UPDATE_OFF"] = "1"
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.5)
    for t in ("WM_SNAP_C", "WM_SNAP_D", "WM_SNAP_E"):
        h = wm.find_window_by_title(t)
        if h:
            wm.force_kill_pid(wm.pid_of(h))
    time.sleep(0.5)

    wa = wm.pick_test_monitor().rcWork
    w13 = (wa.Right - wa.Left) // 3
    procs = []
    hs = {}
    for t in ("WM_SNAP_C", "WM_SNAP_D", "WM_SNAP_E"):
        procs.append(subprocess.Popen([sys.executable, str(TARGET_SCRIPT), t], env=wm.host_env()))
        hs[t] = wait_window(t)
    time.sleep(0.3)
    for t, target in (("WM_SNAP_C", (wa.Left, wa.Top, wa.Left + w13, wa.Bottom)),
                      ("WM_SNAP_D", (wa.Left + w13, wa.Top, wa.Left + w13 * 2, wa.Bottom)),
                      ("WM_SNAP_E", (wa.Left + w13 * 2, wa.Top, wa.Right, wa.Bottom))):
        ok = efb_align(hs[t], target)
        e = wm.ext_frame_bounds(hs[t])
        print(f"{t}: align={ok} efb=({e.Left},{e.Top})-({e.Right},{e.Bottom}) "
              f"expect={target} zoomed={wm.is_zoomed(hs[t])}")

    p = subprocess.run([EXE, "--detect-snap"], capture_output=True, timeout=30)
    print("detect:", p.stdout.decode("utf-8", errors="replace").strip().splitlines()[-1])
    for pr in procs:
        pr.terminate()
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
