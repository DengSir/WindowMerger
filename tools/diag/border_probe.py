# -*- coding: utf-8 -*-
r"""顶条底边厚度对比测量：同一宿主在 正常态（分隔线=格子边框顶线）与 最大化浮层态
（新增底边）各扫 ThemeBorder 色带宽度（物理 px），数字对比"是不是一样粗"。
暗色主题固定（写 config），测完还原。用法: uv run tools/diag/border_probe.py
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402

BORDER_T = (58, 58, 58)  # ThemeBorder 暗色


def scan_runs(img, col: int, ymax: int = 70) -> list[tuple[int, int]]:
    runs, y, inrun, start = [], 0, False, 0
    while y < min(ymax, img.size[1]):
        is_b = wm.color_close(img.getpixel((col, y))[:3], BORDER_T, tol=10)
        if is_b and not inrun:
            inrun, start = True, y
        if not is_b and inrun:
            runs.append((start, y - start))
            inrun = False
        y += 1
    if inrun:
        runs.append((start, y - start))
    return runs


def measure(hm: int, tag: str) -> None:
    img = wm.capture_window(hm)
    col = img.size[0] // 4  # 左格内部：避开居中分隔条（divider 60 色 tol=10 会误判成 border）
    print(f"{tag} dpi={wm.get_dpi_for_window(hm)} img={img.size} col={col} "
          f"BORDER_RUNS={scan_runs(img, col)}")
    top = " ".join(f"{y}:{img.getpixel((col, y))[:3]}" for y in range(0, 8))
    mid = " ".join(f"{y}:{img.getpixel((col, y))[:3]}" for y in range(24, 32))
    print(f"  rows0-7 {top}")
    print(f"  rows24-31 {mid}")


def main() -> int:
    cp = wm.config_path()
    backup = Path(cp).read_text(encoding="utf-8") if os.path.exists(cp) else None
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    wm.save_config({"Theme": "Dark"})  # 固定暗色：Border=(58,58,58) 可色带扫描
    proc = subprocess.Popen([wm.exe_path()], env=wm.host_env())
    if not wm.wait_until(lambda: bool(wm.main_windows_of_pid(proc.pid)), 15000):
        print("NO_HOST")
        return 1
    hm = wm.main_windows_of_pid(proc.pid)[0]
    wa = wm.pick_test_monitor().rcWork
    wm.set_window_pos(hm, None, wa.Left + 20, wa.Top + 20, 900, 500, wm.SWP_NOZORDER)
    time.sleep(1.0)

    measure(hm, "NORMAL")
    wm.show_window(hm, 3)  # SW_MAXIMIZE
    time.sleep(1.2)
    wm.set_cursor_pos(wa.Left + 20 + 450, wa.Top + 2)  # 触顶唤出顶条滑入（条内中部不再触发，issue #1）
    time.sleep(0.7)  # 轮询 100ms + 滑入 120ms 裕量
    measure(hm, "MAXIMIZED")

    # 跨 DPI 复测：主屏非 96 时挪过去再来一轮（150% 下 2 DIP = 3px）
    try:
        mi = next(m for m in wm.monitors() if wm.monitor_dpi(m) != 96)
    except StopIteration:
        mi = None
    if mi is not None:
        r = mi.rcWork
        wm.set_window_pos(hm, None, r.Left + 20, r.Top + 20, 0, 0,
                          wm.SWP_NOSIZE | wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
        time.sleep(1.0)  # 跨 DPI 两步收敛
        wm.show_window(hm, wm.SW_RESTORE)
        time.sleep(1.0)
        wm.set_window_pos(hm, None, r.Left + 20, r.Top + 20, 900, 500, wm.SWP_NOZORDER)
        time.sleep(1.0)
        measure(hm, "NORMAL@150")
        wm.show_window(hm, 3)
        time.sleep(1.2)
        wm.set_cursor_pos(r.Left + 20 + 450, r.Top + 2)  # 触顶唤出（同上，issue #1）
        time.sleep(0.7)
        measure(hm, "MAXIMIZED@150")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    if backup is not None:
        Path(cp).write_text(backup, encoding="utf-8")
    elif os.path.exists(cp):
        os.remove(cp)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
