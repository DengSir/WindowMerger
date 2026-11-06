# -*- coding: utf-8 -*-
"""全流程回归：清理 → 开测试窗 → CLI 吸附 → 命中/矩形断言 → 还原置顶。原 RunTestFlow.ps1。
用法: py tools\\tests\\run_test_flow.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint（含用户自己开着的实例）。
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 1. 清理
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    Path(tempfile.gettempdir(), "wm-composite.log").unlink(missing_ok=True)

    # 2. 测试窗口
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t2 = Path(tempfile.gettempdir(), "wmt2.txt")
    t1.write_text("cli-test-1", encoding="ascii")
    t2.write_text("cli-test-2", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(0.7)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)

    # 3. 带命名参数启动宿主
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)

    hm = wm.host_hwnd()
    if not hm:
        print("FAIL host-not-running")
        return 1
    hr = wm.get_window_rect(hm)
    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")

    # 4. 左右格中心命中（内容宽 0.25/0.75；旧 0.5 探点落在分界上会探错格）
    avail = hr.Right - hr.Left - 4 - 8
    mid_y = (hr.Top + hr.Bottom) // 2
    h1 = wm.window_from_point(int(hr.Left + 2 + avail * 0.25), mid_y)
    print(f"LEFT_HIT proc={wm.proc_name_of(h1)}")
    h2 = wm.window_from_point(int(hr.Left + 2 + avail * 0.75), mid_y)
    print(f"RIGHT_HIT proc={wm.proc_name_of(h2)}")

    # 5. 子窗口矩形 vs 格子（外扩 7/0/7/7）
    try:
        ratio = float(wm.load_config().get("Ratio", 0.5))
    except Exception:
        ratio = 0.5
    pane_w = int(avail * ratio)
    exp_l = (hr.Left + 2 - 7, hr.Top + 2 + 28 - 0, hr.Left + 2 + pane_w + 7, hr.Bottom - 2 + 7)
    for _, h in wm.main_windows_by_name("Notepad"):
        r = wm.get_window_rect(h)
        dev = sum(abs(v - e) for v, e in zip(r.as_tuple(), exp_l))
        print(f"LEFT_CHILD rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) paneDeviation={dev}")
    exp_r0 = hr.Left + 2 + pane_w + 8 - 7
    for _, h in wm.main_windows_by_name("mspaint"):
        r = wm.get_window_rect(h)
        dev = (abs(r.Left - exp_r0) + abs(r.Top - (hr.Top + 30))
               + abs(r.Right - (hr.Right - 2 + 7)) + abs(r.Bottom - (hr.Bottom - 2 + 7)))
        print(f"RIGHT_CHILD rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) paneDeviation={dev}")

    # 6. 不残留置顶
    wm.set_topmost(hm, False)
    print("FLOW_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
