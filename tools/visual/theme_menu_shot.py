# -*- coding: utf-8 -*-
"""主题下拉视觉检查：启动 → 置顶 → 真实点击主题按钮 → 截展开菜单 → ESC +
NOTOPMOST + 优雅关。原 ThemeMenuShot.ps1。
用法: py tools\\visual\\theme_menu_shot.py
截图: %TEMP%\\wm_thememenu.png
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

VK_ESC = 0x1B


def main() -> int:
    subprocess.Popen([wm.exe_path()])
    time.sleep(3)

    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hr = wm.get_window_rect(hm)
    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")

    # 置顶让真实点击落在宿主上（Atomic 模式；后面还原）
    wm.set_topmost(hm, True)
    time.sleep(0.3)

    bx = hr.Right - 4 - 139
    by = hr.Top + 16
    wm.set_cursor_pos(bx, by)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.06)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(0.8)

    # 全屏截（菜单是独立弹层，PrintWindow 截不到）后裁按钮+下拉区
    big = wm.capture_screen(0, 0, 2560, 1440)
    cap_w, cap_h = 420, 260
    cap_x = max(0, bx - 340)
    cap_y = max(0, hr.Top)
    small = big.crop((cap_x, cap_y, cap_x + cap_w, cap_y + cap_h))
    small.save(str(Path(tempfile.gettempdir(), "wm_thememenu.png")))
    print(f"SHOT {cap_w}x{cap_h} at ({cap_x},{cap_y})")

    # 关菜单、还原 NOTOPMOST、优雅关
    wm.keybd_event(VK_ESC, 0, 0)
    time.sleep(0.2)
    wm.keybd_event(VK_ESC, 0, 2)
    time.sleep(0.3)
    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("MENU_SHOT_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
