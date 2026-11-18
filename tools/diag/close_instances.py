"""优雅关闭所有 WindowMerger 实例：WM_CLOSE 逐窗（各宿主 OnClosing 还原子窗+落盘），
进程若因托盘常驻未退，再确认无吸附子窗后收尾杀托盘残留。诊断工具，勿用于日常。"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import wm  # noqa: E402

pids = wm.pids_by_name("WindowMerger")
if not pids:
    print("NO_INSTANCE")
    sys.exit(0)
wins = wm.top_windows_of_pids(pids)
for h in wins:
    print(f"WM_CLOSE -> {h:X} (pid {wm.pid_of(h)}) title={wm.get_text(h)!r}")
    wm.post_close(h)
deadline = time.monotonic() + 8
while time.monotonic() < deadline:
    alive = [p for p in pids if p in wm.pids_by_name("WindowMerger")]
    if not alive:
        print("EXITED_GRACEFULLY")
        sys.exit(0)
    time.sleep(0.3)
alive = [p for p in pids if p in wm.pids_by_name("WindowMerger")]
print("TRAY_RESIDUE", alive)
sys.exit(0)
