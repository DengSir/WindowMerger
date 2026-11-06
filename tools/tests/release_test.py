# -*- coding: utf-8 -*-
"""释放路径回归：CLI 吸附 notepad+mspaint → UIA Invoke 释放按钮（顶条第 4 个）→
两者必须摘掉 TOOLWINDOW 且窗口完好（AttachedChild.Restore）。原 ReleaseTest.ps1。
用法: py tools\\tests\\release_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 自备环境：清理 → 测试窗 → CLI 吸附（不依赖 run_test_flow 留下的现场）
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("release-test", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)

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

    states = [(proc, wm.is_toolwindow(h)) for proc, h in wm.main_windows_by_name("Notepad", "mspaint")]
    for proc, tool in states:
        print(f"{proc} tool={tool}")
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    print("RELEASE_TEST_DONE")
    ok = bool(states) and all(not tool for _, tool in states)
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
