# -*- coding: utf-8 -*-
"""notepad 双窗时机排查：杀 → 起 → 分阶段枚举窗口数，定位第二窗出现的时间点与进程。"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

wm.force_kill_by_name("Notepad")
time.sleep(0.5)
t1 = Path(wm.tempfile_dir() if hasattr(wm, "tempfile_dir") else Path(__file__).parent, "np_probe.txt")
t1.write_text("probe", encoding="ascii")
subprocess.Popen(["notepad", str(t1)])
for step in range(8):
    wins = []
    for pid in wm.pids_by_name("notepad"):
        for h in wm.main_windows_of_pid(pid):
            r = wm.get_window_rect(h)
            wins.append(f"pid={pid} hwnd={h} {wm.get_text(h)!r} @({r.Left},{r.Top})")
    print(f"t+{step * 0.75:.2f}s windows={len(wins)} {wins}")
    time.sleep(0.75)
wm.force_kill_by_name("Notepad")
