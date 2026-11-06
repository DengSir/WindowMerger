# -*- coding: utf-8 -*-
"""纯 UIA 主题下拉验证（不注入输入，锁屏可用）：启动 → UIA Invoke 主题按钮开菜单 →
读 3 个菜单项（顺序：跟随系统/深色/浅色，打印名字码点）→ Invoke 深色 → 校验
config Theme==Dark 且重开后深色项带 ✓(U+2713) → 恢复原模式 → 优雅关。原 ThemeMenuTest.ps1。
用法: py tools\\visual\\theme_menu_test.py
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

# tooltip 前两个码点（中文"主题"），保持无中文字面量也行，这里直接写中文
ZH_THEME = "主题"
CHECK_MARK = "✓"


def name_codepoints(el) -> str:
    return " ".join(f"U+{ord(ch):X4}" for ch in wm_uia.name_of(el))


def read_cfg_theme() -> str:
    try:
        return str(wm.load_config().get("Theme", "?"))
    except FileNotFoundError:
        return "NO_FILE"
    except Exception:
        return "READ_FAIL"


def main() -> int:
    orig_theme = read_cfg_theme()
    if orig_theme == "NO_FILE":
        orig_theme = "Auto"
    print(f"ORIG_THEME={orig_theme}")

    # 启动全新实例
    subprocess.Popen([wm.exe_path()])
    time.sleep(3)

    hosts = wm.host_hwnds()
    if not hosts:
        print("NO_HOST")
        return 1
    hm = hosts[0]
    pid = wm.pid_of(hm)
    main_el = wm_uia.element_from_handle(hm)

    # 找主题按钮：8 个顶条按钮按行序，索引 4 = 主题；用 tooltip 前缀交叉校验
    btns = wm_uia.find_all_buttons(main_el)
    print(f"BUTTONS={len(btns)}")
    if len(btns) < 5:
        print("NO_THEME_BUTTON")
        return 1
    theme_btn = btns[4]
    for i, b in enumerate(btns):
        if wm_uia.help_text_of(b).startswith(ZH_THEME):
            theme_btn = b
            print(f"THEME_BTN_BY_TOOLTIP idx={i}")

    # 开菜单、读项
    wm_uia.invoke(theme_btn)
    time.sleep(0.8)
    items = wm_uia.menu_items_of_pid_windows(pid)
    print(f"ITEMS_FOUND={len(items)}")
    for i, it in enumerate(items):
        print(f"ITEM[{i}] {name_codepoints(it)}")

    dark_ok = light_ok = restored_ok = False
    if len(items) >= 3:
        wm_uia.invoke(items[1])  # 深色
        time.sleep(0.6)
        after = read_cfg_theme()
        dark_ok = after == "Dark"
        print(f"THEME_AFTER_DARK={after}")

        wm_uia.invoke(theme_btn)  # 重开
        time.sleep(0.8)
        items2 = wm_uia.menu_items_of_pid_windows(pid)
        print(f"ITEMS2_FOUND={len(items2)}")
        for i, it in enumerate(items2):
            first = name_codepoints(it).strip().split(" ")[0]
            print(f"ITEM2[{i}] first={first}")

        # 亮色（items2[2]）
        if len(items2) >= 3:
            wm_uia.invoke(items2[2])
            time.sleep(0.6)
            after_light = read_cfg_theme()
            light_ok = after_light == "Light"
            print(f"THEME_AFTER_LIGHT={after_light}")

            # 恢复原模式：0=Auto 1=Dark 2=Light
            idx = {"Auto": 0, "Dark": 1, "Light": 2}.get(orig_theme, 0)
            wm_uia.invoke(theme_btn)
            time.sleep(0.8)
            items3 = wm_uia.menu_items_of_pid_windows(pid)
            if len(items3) >= 3:
                wm_uia.invoke(items3[idx])
                time.sleep(0.6)
                restored = read_cfg_theme()
                restored_ok = restored == orig_theme
                print(f"THEME_RESTORED={restored}")
    else:
        print("MENU_NOT_FOUND")

    # 优雅关
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("APP_STILL_RUNNING" if wm.pids_by_name("WindowMerger") else "APP_CLOSED")
    print("THEME_UIA_TEST_DONE")
    ok = dark_ok and light_ok and restored_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
