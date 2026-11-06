# -*- coding: utf-8 -*-
"""优雅关 WindowMerger（exe 解锁重建用）+ 强杀测试窗（notepad/mspaint）。原 CloseInstance.ps1。
用法: py tools\\utils\\close_instance.py
警告: notepad 是强杀，未保存内容会丢——跑之前确认没有正在使用的窗口。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    wm.force_kill_by_name("Notepad", "mspaint")
    time.sleep(1.5)
    print("STILL_RUNNING" if wm.pids_by_name("WindowMerger") else "CLOSED_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
