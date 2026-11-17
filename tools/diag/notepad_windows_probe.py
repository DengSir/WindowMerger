# -*- coding: utf-8 -*-
"""run_test_flow LEFT_CHILD 双记事本窗排查：枚举 notepad 全部顶层窗（标题/矩形/pid）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

for proc, h in wm.main_windows_by_name("Notepad"):
    r = wm.get_window_rect(h)
    print(f"{proc} hwnd={h} pid={wm.pid_of(h)} rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) "
          f"title={wm.get_text(h)!r} visible={wm.is_window_visible(h)} attached={wm.is_attached(h)}")
print(f"PIDS={wm.pids_by_name('notepad')}")
