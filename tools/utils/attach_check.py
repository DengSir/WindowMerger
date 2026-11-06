# -*- coding: utf-8 -*-
"""吸附状态确定性校验：TOOLWINDOW 样式 + 矩形（无屏幕探针）。原 AttachCheck.ps1。
用法: uv run tools/\utils\\attach_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    hosts = wm.host_hwnds()
    if not hosts:
        print("NO_HOST")
        return 1
    hm = hosts[0]
    hr = wm.get_window_rect(hm)
    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")

    try:
        ratio = float(wm.load_config().get("Ratio", 0.5))
    except Exception:
        ratio = 0.5
    pane_w = int((hr.Right - hr.Left - 4 - 8) * ratio)

    for proc, h in wm.main_windows_by_name("Notepad", "mspaint"):
        tool = wm.is_toolwindow(h)
        r = wm.get_window_rect(h)
        print(f"{proc} tool={tool} rect=({r.Left},{r.Top})-({r.Right},{r.Bottom})")
        if proc == "notepad":
            # 预期左格: L=hr.L+2-7, T=hr.T+2+28, R=hr.L+2+paneW+7, B=hr.B-2+7（7px 隐形边外扩）
            exp = (hr.Left + 2 - 7, hr.Top + 2 + 28, hr.Left + 2 + pane_w + 7, hr.Bottom - 2 + 7)
            dev = sum(abs(a - b) for a, b in zip(r.as_tuple(), exp))
            print(f"  LEFT_PANE_DEV={dev}")
        if proc == "mspaint":
            exp = (hr.Left + 2 + pane_w + 8 - 7, hr.Top + 2 + 28, hr.Right - 2 + 7, hr.Bottom - 2 + 7)
            dev = sum(abs(a - b) for a, b in zip(r.as_tuple(), exp))
            print(f"  RIGHT_PANE_DEV={dev}")
    print("ATTACH_CHECK_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
