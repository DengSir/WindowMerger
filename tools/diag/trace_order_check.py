# -*- coding: utf-8 -*-
"""诊断：WM_TRACE=1 跑一次 snap 直连流，打印宿主侧事件时间线。
验证顺序之争：OnSourceInitialized(测试2) vs Loaded/AttachStartupTargets(测试) 谁先。

用法: uv run tools/diag/trace_order_check.py
"""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

os.environ["WM_TRACE"] = "1"
EXE = wm.exe_path()
TARGET = Path(__file__).resolve().parents[1] / "targets" / "snap_target.py"


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.5)
    log = os.path.join(os.environ["TEMP"], "wm_trace.log")
    open(log, "w").close()

    procs = [subprocess.Popen([sys.executable, str(TARGET), "WM_TR_A"], env=dict(os.environ)),
             subprocess.Popen([sys.executable, str(TARGET), "WM_TR_B"], env=dict(os.environ))]
    time.sleep(1.2)
    ha = wm.find_window_by_title("WM_TR_A")
    hb = wm.find_window_by_title("WM_TR_B")
    p = subprocess.Popen([EXE, "--left-hwnd", str(ha), "--right-hwnd", str(hb),
                          "--profile", "snap-trace"], env=dict(os.environ))
    ok = wm.wait_until(lambda: wm.is_attached(ha) and wm.is_attached(hb), 10000, 200)
    time.sleep(1.5)
    wins = wm.main_windows_of_pid(p.pid)
    if wins:
        wm.post_close(wins[0])
    wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
    for pr in procs:
        pr.terminate()
    time.sleep(0.5)
    print(f"attached: {ok}")
    print("--- %TEMP%\\wm_trace.log ---")
    print(open(log, encoding="utf-8").read())
    os.remove(log)
    Path(wm.config_path().replace("config.json", "config-snap-trace.json")).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
