# -*- coding: utf-8 -*-
"""multi_win 靶窗启动诊断：Popen 后捕获 stderr/窗口枚举。"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

p = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1]
                                          / "targets" / "multi_win.py")],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(3.0)
alive = p.poll() is None
print(f"alive={alive} returncode={p.poll()}")
try:
    out, err = p.communicate(timeout=2)
    print(f"stdout={out!r} stderr={err!r}")
except subprocess.TimeoutExpired:
    print("still running (mainloop), no early exit")
wins = wm.top_windows_of_pids([p.pid])
print(f"top_windows={[(wm.get_text(h), wm.get_class_name(h)) for h in wins]}")
print(f"all_windows={[(wm.get_text(h), wm.get_class_name(h)) for h in wm.all_windows_of_pid(p.pid)]}")
p.kill()
