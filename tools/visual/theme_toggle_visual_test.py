# -*- coding: utf-8 -*-
"""UIA 切主题：Invoke 主题按钮 → 从弹层 Invoke "浅色"/"深色" 菜单项，每次应用后
PrintWindow 截顶条条带（%TEMP%\\wm_theme_s*.png）。原 ThemeToggleVisualTest.ps1。
用法: py tools\\visual\\theme_toggle_visual_test.py
警告: 强杀运行中的 WindowMerger 实例。
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

ZH_THEME = "主题"
ZH_LIGHT = "浅色"
ZH_DARK = "深色"


def snap(hm, tag: str) -> None:
    img = wm.capture_window(hm)
    strip = img.crop((0, 0, img.width, 30))
    strip.save(str(Path(tempfile.gettempdir(), f"wm_theme_{tag}.png")))
    print(f"SHOT_{tag}")


def invoke_menu_item(pid: int, name_suffix: str) -> bool:
    time.sleep(0.5)
    # 弹层菜单属于本进程；全进程顶层窗口里按名后缀找
    for it in wm_uia.menu_items_of_pid_windows(pid):
        if wm_uia.name_of(it).endswith(name_suffix):
            wm_uia.invoke(it)
            return True
    return False


def main() -> int:
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    subprocess.Popen([wm.exe_path()])
    time.sleep(3)

    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    pid = wm.pid_of(hm)
    main_el = wm_uia.element_from_handle(hm)

    theme_btn = None
    for b in wm_uia.find_all_buttons(main_el):
        if wm_uia.help_text_of(b).startswith(ZH_THEME):
            theme_btn = b
            break
    if theme_btn is None:
        print("NO_THEME_BUTTON")
        return 1

    snap(hm, "s0")

    # 开菜单 + Invoke 浅色
    wm_uia.invoke(theme_btn)
    print(f"LIGHT_INVOKE={invoke_menu_item(pid, ZH_LIGHT)}")
    time.sleep(0.6)
    snap(hm, "s1")

    # 开菜单 + Invoke 深色
    wm_uia.invoke(theme_btn)
    print(f"DARK_INVOKE={invoke_menu_item(pid, ZH_DARK)}")
    time.sleep(0.6)
    snap(hm, "s2")

    # 读配置确认持久化
    print(f"CONFIG_THEME={wm.load_config().get('Theme')}")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("THEME_TOGGLE_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
