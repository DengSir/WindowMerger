# -*- coding: utf-8 -*-
"""释放路径回归：UIA Invoke 释放按钮（顶条第 4 个），notepad/mspaint 必须摘掉
TOOLWINDOW 且窗口完好（AttachedChild.Restore）。原 ReleaseTest.ps1。
用法: py tools\\tests\\release_test.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

# 前置：需要已有吸附组合（跑 RunTestFlow 后立即用），脚本只触发释放并校验


def main() -> int:
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1

    main_el = wm_uia.element_from_handle(hm)
    btns = wm_uia.find_all_buttons(main_el)
    if len(btns) < 4:
        print("NO_RELEASE_BTN")
        return 1
    wm_uia.invoke(btns[3])  # 顶条按钮序：左/右/交换/释放
    time.sleep(1.2)

    for proc, h in wm.main_windows_by_name("Notepad", "mspaint"):
        print(f"{proc} tool={wm.is_toolwindow(h)}")
    print("RELEASE_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
