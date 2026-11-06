# -*- coding: utf-8 -*-
"""悬停视觉测试：光标移到 分隔条/远离/最大化/关闭 上，各 PrintWindow 截顶条条带。
强制深色保证颜色确定（结束恢复 Auto）。原 HoverVisualTest.ps1。
用法: py tools\\visual\\hover_visual_test.py
警告: 强杀运行中的 WindowMerger；需 notepad/mspaint 可被 CLI 吸附。
截图: %TEMP%\\wm_hover_*.png
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    # 强制深色（确定性预期；结束恢复 Auto）
    cfg = wm.load_config()
    cfg["Theme"] = "Dark"
    cfg["Ratio"] = 0.5
    wm.save_config(cfg)

    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    subprocess.Popen([wm.exe_path(), "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)

    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hr = wm.get_window_rect(hm)
    w = hr.width
    wm.set_topmost(hm, True)  # 悬停才能到达宿主
    time.sleep(0.4)

    def snap(tag: str) -> None:
        time.sleep(0.4)
        img = wm.capture_window(hm)
        strip = img.crop((0, 0, w, 30))
        strip.save(str(Path(tempfile.gettempdir(), f"wm_hover_{tag}.png")))
        print(f"SHOT_{tag}")

    # 分隔条中心（比例 0.5）
    avail = w - 4 - 8
    wm.set_cursor_pos(int(hr.Left + 2 + avail * 0.5 + 4), (hr.Top + hr.Bottom) // 2)
    snap("divider")

    # 移开 → 基态（分隔条不得残留高亮/透明）
    wm.set_cursor_pos(6, 700)
    snap("away")

    # 最大化按钮（普通悬停：浅灰）
    wm.set_cursor_pos(hr.Right - 60, hr.Top + 16)
    snap("max")

    # 关闭按钮（危险悬停：红）
    wm.set_cursor_pos(hr.Right - 22, hr.Top + 16)
    snap("close")

    # 再移开
    wm.set_cursor_pos(6, 700)
    snap("away2")

    wm.set_topmost(hm, False)

    # 恢复用户设置
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)
    print("HOVER_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
