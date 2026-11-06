# -*- coding: utf-8 -*-
"""交互式最大化拖动验证：脚本准备环境（新宿主 + notepad/mspaint 吸附），**人工**操作：
最大化 → 顶条原地点击 → 拖顶条。期间每 150ms 采样窗口状态到时间线，回本控制台按
ENTER 结束并打印状态迁移。原 ManualDragTest.ps1。
用法: uv run tools/\tests\\manual_drag_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    import msvcrt

    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 1. 环境：清理 + 全新配置 + 测试窗 + 带子窗口的宿主
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("manual-drag-1", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(0.7)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)

    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    print(f"HOST 0x{hm:X} ready.")
    print("OPERATE NOW: maximize -> click top bar (no move) -> drag top bar. Press ENTER when done.")

    # 2. 每 150ms 采样直到按 ENTER（msvcrt 轮询，等价 Console.KeyAvailable）
    log: list[str] = []
    start = time.monotonic()
    done = False
    while not done:
        r = wm.get_window_rect(hm)
        z = wm.is_zoomed(hm)
        c = wm.get_cursor_pos()
        log.append(f"{int((time.monotonic() - start) * 1000):>6} ms  zoomed={z!s:<5} "
                   f"rect=({r.Left},{r.Top})-({r.Right},{r.Bottom})  cursor=({c[0]},{c[1]})")
        while msvcrt.kbhit():
            if msvcrt.getwch() == "\r":
                done = True
        time.sleep(0.15)

    # 3. 汇总：只打印状态变化行
    print()
    print("--- transitions (state changes only) ---")
    prev = ""
    for line in log:
        cur = line.split("ms  ", 1)[1]
        if cur != prev:
            print(line)
            prev = cur
    print(f"SAMPLES={len(log)}")

    # 4. 窗口留给用户检查；宿主需手动关或由下次测试清掉
    print("MANUAL_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
