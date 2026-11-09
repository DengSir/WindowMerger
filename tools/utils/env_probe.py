# -*- coding: utf-8 -*-
"""探测本机显示器布局与 DPI（布局重构前的环境基线）。"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import wm

print(f"primary_work_area = {wm.primary_work_area().as_tuple()}")
for i, mi in enumerate(wm.monitors()):
    r, w = mi.rcMonitor, mi.rcWork
    print(f"monitor[{i}]: rcMonitor={r.as_tuple()} rcWork={w.as_tuple()} "
          f"primary={bool(mi.dwFlags & 1)}")
print(f"left_monitor_work_area = {wm.left_monitor_work_area().as_tuple()}")
print(f"SM_CXSCREEN={wm.get_system_metrics(wm.SM_CXSCREEN)} "
      f"SM_CYSCREEN={wm.get_system_metrics(wm.SM_CYSCREEN)}")
print(f"virtual = {wm.virtual_screen_bounds()}")
