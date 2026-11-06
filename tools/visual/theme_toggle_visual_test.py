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
    # 顶条像素断言（x=60 在文字上方干净区）：PrintWindow 渲染色 = 调色板值
    px = img.getpixel((60, 5))
    print(f"SHOT_{tag} bar_rgb=({px[0]},{px[1]},{px[2]})")
    snap.bar_rgb = px[:3]


def invoke_menu_item(pid: int, idx: int) -> bool:
    """按索引 Invoke 菜单项（0=跟随系统 1=深色 2=浅色）。自定义 Header 的 MenuItem
    UIA Name 为空（实测），不能按名匹配。"""
    time.sleep(0.5)
    items = wm_uia.menu_items_of_pid_windows(pid)
    if len(items) > idx:
        wm_uia.invoke(items[idx])
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

    # 开菜单 + Invoke 浅色（索引 2）
    wm_uia.invoke(theme_btn)
    print(f"LIGHT_INVOKE={invoke_menu_item(pid, 2)}")
    time.sleep(0.6)
    snap(hm, "s1")
    light_ok = wm.color_close(snap.bar_rgb, wm.PALETTES["Light"]["Bar"])

    # 开菜单 + Invoke 深色（索引 1）
    wm_uia.invoke(theme_btn)
    print(f"DARK_INVOKE={invoke_menu_item(pid, 1)}")
    time.sleep(0.6)
    snap(hm, "s2")
    dark_ok = wm.color_close(snap.bar_rgb, wm.PALETTES["Dark"]["Bar"])

    # 读配置确认持久化
    cfg_theme = wm.load_config().get("Theme")
    cfg_ok = cfg_theme == "Dark"
    print(f"CONFIG_THEME={cfg_theme}")

    # 恢复用户主题设置
    cfg = wm.load_config()
    cfg["Theme"] = "Auto"
    wm.save_config(cfg)

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("THEME_TOGGLE_TEST_DONE")
    ok = light_ok and dark_ok and cfg_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
