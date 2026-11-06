# -*- coding: utf-8 -*-
"""按 hwnd 执行 minimize/restore/close。原 WinCmd.ps1。
用法: py tools\\utils\\win_cmd.py --hwnd N --action minimize|restore|close
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwnd", type=lambda v: int(v, 0), default=0)
    ap.add_argument("--action", required=True, choices=["minimize", "restore", "close"])
    a = ap.parse_args()

    h = a.hwnd
    if h == 0:
        print("NOT_FOUND")
        return 1

    if a.action == "minimize":
        wm.show_window(h, wm.SW_MINIMIZE)
    elif a.action == "restore":
        wm.show_window(h, wm.SW_RESTORE)
    else:
        wm.post_close(h)
    time.sleep(0.4)
    print(f"CMD_OK {a.action} hwnd={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
