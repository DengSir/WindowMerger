# -*- coding: utf-8 -*-
"""列出运行中 WindowMerger 实例的启动时间。原 InstanceTimes.ps1。
用法: uv run tools/\utils\\instance_times.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    for pid in wm.pids_by_name("WindowMerger"):
        st = wm.proc_start_time(pid)
        print(f"PID={pid} START={st.strftime('%H:%M:%S') if st else '?'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
