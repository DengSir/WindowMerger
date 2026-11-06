# -*- coding: utf-8 -*-
"""吸附/释放循环的幽灵任务栏按钮检查（v2）。每轮：吸附 → UIA Invoke 释放 →
(a) dump 任务栏按钮 (b) dump 有标题+无主+非 TOOLWINDOW 顶层窗口（含
vis/iconic/cloaked/rect）——任务栏条目对应窗口隐藏/屏外 = 幽灵。
最终全杀测试应用再 dump：死应用的按钮 = 点击无反应的陈旧 shell 条目。
原 GhostCycleTest.ps1。
用法: py tools\\tests\\ghost_cycle_test.py [--exe 路径] [--rounds 5]
警告: 会强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia


def dump_windows(tag: str) -> None:
    print(f"--- titled unowned non-toolwindows {tag} ---")
    for i, h in enumerate(wm.z_walk()):
        if i >= 400:
            break
        ex = wm.get_ex_style(h)
        owned = wm.get_window(h, wm.GW_OWNER) != 0
        if (ex & wm.WS_EX_TOOLWINDOW) == 0 and not owned:
            title = wm.get_text(h, 64)
            if title:
                r = wm.get_window_rect(h)
                vis = wm.is_window_visible(h)
                ic = wm.is_iconic(h)
                cl = wm.cloaked_raw(h)
                off = r.Right <= -30000 or r.Left <= -30000
                print(f"0x{h:X} {wm.proc_name_of(h):<9} vis={vis!s:<5} iconic={ic!s:<5} "
                      f"cloaked={cl} off={off} rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) "
                      f"class={wm.get_class_name(h, 48)} title=[{title}]")


def dump_taskbar_buttons(tag: str) -> None:
    print(f"--- taskbar buttons {tag} ---")
    try:
        for n in wm_uia.dump_taskbar_buttons():
            print(f"BTN [{n}]")
    except Exception as e:
        print(f"NO_TASKBAR ({e})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    ap.add_argument("--rounds", type=int, default=5)
    a = ap.parse_args()

    for rnd in range(1, a.rounds + 1):
        print(f"===== ROUND {rnd} =====")
        wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
        time.sleep(0.7)
        t1 = Path(tempfile.gettempdir(), "wmt1.txt")
        t1.write_text(f"ghost-r{rnd}", encoding="ascii")
        subprocess.Popen(["notepad", str(t1)])
        time.sleep(0.6)
        subprocess.Popen(["mspaint"])
        time.sleep(1.4)
        subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
        time.sleep(4)
        hm = wm.host_hwnd()
        if not hm:
            print("NO_HOST")
            continue
        main_el = wm_uia.element_from_handle(hm)
        btns = wm_uia.find_all_buttons(main_el)
        if len(btns) < 4:
            print("NO_RELEASE_BTN")
            continue
        wm_uia.invoke(btns[3])  # 释放按钮
        time.sleep(1.5)
        dump_taskbar_buttons(f"R{rnd}")
        dump_windows(f"R{rnd}")

    print("===== FINAL: kill test apps, check for stale buttons =====")
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(2.5)
    dump_taskbar_buttons("AFTER_KILL")
    print("GHOST_CYCLE2_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
