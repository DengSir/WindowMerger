# -*- coding: utf-8 -*-
"""全流程回归：清理 → 开测试窗 → CLI 吸附 → 命中/矩形断言 → 还原置顶。原 RunTestFlow.ps1。
用法: uv run tools/\tests\\run_test_flow.py [--exe 路径]
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

    # 3. 带命名参数启动宿主 + 固定布局钉位（主屏，命中/矩形断言坐标静态可推）
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)

    hm = wm.host_hwnd()
    if not hm:
        print("FAIL host-not-running")
        return 1
    wm.set_window_pos(hm, None, 400, 150, 2200, 900, wm.SWP_NOZORDER)
    time.sleep(1.5)  # 维护定时器把子窗口搬进新格子
    hr = wm.get_window_rect(hm)
    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")

    # 4. 左右格中心命中（内容宽 0.25/0.75；旧 0.5 探点落在分界上会探错格）；置顶防前台干扰
    wm.set_topmost(hm, True)
    time.sleep(0.4)
    avail = hr.Right - hr.Left - 4 - 8
    mid_y = (hr.Top + hr.Bottom) // 2
    h1 = wm.window_from_point(int(hr.Left + 2 + avail * 0.25), mid_y)
    print(f"LEFT_HIT proc={wm.proc_name_of(h1)}")
    h2 = wm.window_from_point(int(hr.Left + 2 + avail * 0.75), mid_y)
    print(f"RIGHT_HIT proc={wm.proc_name_of(h2)}")
    hits_ok = (wm.proc_name_of(h1).lower() == "notepad"
               and wm.proc_name_of(h2).lower() == "mspaint")

    # 5. 子窗口矩形 vs 格子（常量随宿主屏 DPI 缩放；隐形边 7px@100% ↔ 9px@150%，容差覆盖）
    try:
        ratio = float(wm.load_config().get("Ratio", 0.5))
    except Exception:
        ratio = 0.5
    scale = wm.get_dpi_for_window(hm) / 96.0
    bw, tb, dv, mg = round(2 * scale), round(28 * scale), round(6 * scale), round(7 * scale)
    pane_w = int((hr.Right - hr.Left - 2 * bw - dv) * ratio)
    exp_l = (hr.Left + bw - mg, hr.Top + bw + tb, hr.Left + bw + pane_w + mg, hr.Bottom - bw + mg)
    dev_l = None
    for _, h in wm.main_windows_by_name("Notepad"):
        r = wm.get_window_rect(h)
        dev_l = sum(abs(v - e) for v, e in zip(r.as_tuple(), exp_l))
        print(f"LEFT_CHILD rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) paneDeviation={dev_l}")
    exp_r0 = hr.Left + bw + pane_w + dv - mg
    dev_r = None
    for _, h in wm.main_windows_by_name("mspaint"):
        r = wm.get_window_rect(h)
        dev_r = (abs(r.Left - exp_r0) + abs(r.Top - (hr.Top + bw + tb))
                 + abs(r.Right - (hr.Right - bw + mg)) + abs(r.Bottom - (hr.Bottom - bw + mg)))
        print(f"RIGHT_CHILD rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) paneDeviation={dev_r}")
    rects_ok = (dev_l is not None and dev_l <= 12 and dev_r is not None and dev_r <= 12)

    # 6. 不残留置顶
    wm.set_topmost(hm, False)
    print("FLOW_DONE")
    ok = hits_ok and rects_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
