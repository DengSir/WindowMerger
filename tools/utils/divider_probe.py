# -*- coding: utf-8 -*-
"""分隔条处命中探针：验证宿主盖住子窗口隐形边（分隔条可点击的前提）。原 DividerProbe.ps1。
用法: py tools\\utils\\divider_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hr = wm.get_window_rect(hm)
    try:
        ratio = float(wm.load_config().get("Ratio", 0.5))
    except Exception:
        ratio = 0.5
    avail = hr.Right - hr.Left - 4 - 8
    div_x = int(hr.Left + 2 + avail * ratio + 4)  # 分隔条中心（8px 宽）
    mid_y = (hr.Top + hr.Bottom) // 2
    for dx in range(8):
        h = wm.window_from_point(int(hr.Left + 2 + avail * ratio) + dx, mid_y)
        print(f"DIVIDER+{dx}: {wm.proc_name_of(h)}")
    print(f"DIVIDER_CENTER2 x={div_x}: {wm.proc_name_of(wm.window_from_point(div_x, mid_y))}")
    print("DIVIDER_PROBE_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
