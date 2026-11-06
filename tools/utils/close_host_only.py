# -*- coding: utf-8 -*-
"""只优雅关 WindowMerger（WM_CLOSE，走正常退出流程），不动其他应用。原 CloseHostOnly.ps1。
用法: uv run tools/\utils\\close_host_only.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    print("STILL_RUNNING" if wm.pids_by_name("WindowMerger") else "CLOSED_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
