# -*- coding: utf-8 -*-
"""分隔条悬停检查：分隔条 x 位置中高度竖条（基态/悬停/移开三态 + 像素取色）。
原 DividerHoverTest.ps1。
用法: py tools\\visual\\divider_hover_test.py（对已运行的宿主）
截图: %TEMP%\\wm_divhover_*.png
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    host_pid = wm.pid_of(hm)
    hr = wm.get_window_rect(hm)
    w, h = hr.width, hr.height
    try:
        ratio = float(wm.load_config().get("Ratio", 0.5))
    except Exception:
        ratio = 0.5
    print(f"RATIO={ratio}")
    avail = w - 4 - 8
    div_x = int(hr.Left + 2 + avail * ratio + 4)
    wm.set_topmost(hm, True)
    time.sleep(0.3)

    def snap(tag: str) -> None:
        # 确认光标点确实命中本宿主的分隔条（重试：置顶可能被用户活动窗口顶掉）
        ok = False
        for _ in range(3):
            wm.set_topmost(hm, True)
            time.sleep(0.3)
            wm.set_cursor_pos(div_x, h // 2)
            time.sleep(0.4)
            if wm.pid_of(wm.window_from_point(div_x, h // 2)) == host_pid:
                ok = True
                break
        if not ok:
            print(f"{tag}: SKIP_COVERED")
            return
        img = wm.capture_window(hm)
        lx = div_x - hr.Left
        crop = img.crop((lx - 30, 200, lx + 30, 500))
        crop.save(str(Path(tempfile.gettempdir(), f"wm_divhover_{tag}.png")))
        # 中高度分隔条像素取色
        c = img.getpixel((lx, h // 2))
        print(f"{tag}: divider RGB=({c[0]},{c[1]},{c[2]})")

    wm.set_cursor_pos(6, 700)
    snap("base")
    wm.set_cursor_pos(div_x, h // 2)
    snap("hover")
    wm.set_cursor_pos(6, 700)
    snap("left")

    wm.set_topmost(hm, False)
    print("DIVIDER_HOVER_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
