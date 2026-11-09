# -*- coding: utf-8 -*-
"""pid_fallback 前置探针：parent_pid_of 正确性 / multi_win 窗口枚举 / cmd→notepad 父链。"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

# 1. parent_pid_of 自身正确性：python 自拉子进程，子进程的父应为本进程
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"],
                         creationflags=0x08000000)
time.sleep(1.0)
print(f"child={child.pid} parent_query={wm.parent_pid_of(child.pid)} expect={wm.pid_of(0) if False else 'self'}")
import os
print(f"  -> match self({os.getpid()}): {wm.parent_pid_of(child.pid) == os.getpid()}")
child.kill()

# 2. multi_win 靶窗枚举
target = subprocess.Popen([sys.executable,
                           str(Path(__file__).resolve().parents[1] / "targets" / "multi_win.py")])
for i in range(10):
    time.sleep(0.5)
    wins = wm.top_windows_of_pids([target.pid])
    if wins:
        break
print(f"multi_win pid={target.pid} top_windows={[(wm.get_text(h), wm.get_class_name(h), wm.get_window(h, wm.GW_OWNER)) for h in wins]}")
print(f"  all_windows={[wm.get_text(h) for h in wm.all_windows_of_pid(target.pid)]}")
print(f"  main_windows={wm.main_windows_of_pid(target.pid)}")
target.kill()
time.sleep(0.5)

# 3. cmd /k start notepad 父链
cmd = subprocess.Popen(["cmd", "/k", "start", "", "notepad"],
                       creationflags=0x08000000)
time.sleep(2.5)
nps = wm.main_windows_by_name("Notepad")
for _, h in nps:
    pid = wm.pid_of(h)
    print(f"notepad hwnd={h:X} pid={pid} exe={wm.image_path_of_pid(pid)} "
          f"parent={wm.parent_pid_of(pid)} cmd={cmd.pid} "
          f"grandparent={wm.parent_pid_of(wm.parent_pid_of(pid))}")
wm.force_kill_by_name("Notepad")
wm.force_kill_pid(cmd.pid)
return_code = 0
sys.exit(return_code)
