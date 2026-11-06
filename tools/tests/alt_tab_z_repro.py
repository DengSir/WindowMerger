# -*- coding: utf-8 -*-
"""真实 Alt+Tab z 序复现/回归：宿主（notepad+mspaint 吸附）被最大化 mspaint 全遮 →
Alt+Tab 切回 → 探针确认子窗口升起（TOPBAR/LEFT/RIGHT 命中）。原 AltTabZRepro.ps1。
用法: uv run tools/\tests\\alt_tab_z_repro.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint；注入真实 Alt+Tab，前台 = LockApp 时静默失败。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

VK_MENU, VK_TAB = 0x12, 0x09
SW_MAXIMIZE = 3


def alt_tab_once() -> None:
    wm.keybd_event(VK_MENU, 0, 0)   # ALT down
    time.sleep(0.1)
    wm.keybd_event(VK_TAB, 0, 0)    # TAB down
    time.sleep(0.08)
    wm.keybd_event(VK_TAB, 0, 2)    # TAB up
    time.sleep(0.6)
    wm.keybd_event(VK_MENU, 0, 2)   # ALT up → 切换发生
    time.sleep(0.6)


def probe(tag: str) -> None:
    hm = wm.host_hwnd()
    if not hm:
        print(f"{tag} NO_HOST")
        return
    hr = wm.get_window_rect(hm)
    fg = wm.proc_name_of(wm.get_foreground_window())
    avail = hr.Right - hr.Left - 4 - 8
    mid_y = (hr.Top + hr.Bottom) // 2
    top = wm.proc_name_of(wm.window_from_point((hr.Left + hr.Right) // 2, hr.Top + 14))
    left = wm.proc_name_of(wm.window_from_point(int(hr.Left + 2 + avail * 0.35), mid_y))
    right = wm.proc_name_of(wm.window_from_point(int(hr.Left + 2 + avail * 0.75), mid_y))
    print(f"{tag}: FG={fg} TOPBAR={top} LEFT={left} RIGHT={right}")


def z_dump(tag: str) -> None:
    print(f"--- z-order {tag} (top first, visible only) ---")
    i = 0
    for h in wm.z_walk():
        if i >= 40:
            break
        if wm.is_window_visible(h):
            r = wm.get_window_rect(h)
            print(f"Z{i:<2} {wm.proc_name_of(h):<12} iconic={wm.is_iconic(h)} "
                  f"rect=({r.Left},{r.Top}) [{wm.get_text(h, 96)}]")
            i += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 1. 清理
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)

    # 2. 测试窗口（目标必须先于宿主存在）
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("z-repro-1", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(0.7)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    mps = wm.main_windows_by_name("mspaint")
    if not mps:
        print("FAIL no-mspaint")
        return 1
    mp_h = mps[0][1]

    # 3. 宿主 CLI 吸附
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)
    probe("STEP0_ATTACHED")

    # 最大化 mspaint 全遮宿主，ALT 技巧保前台
    wm.keybd_event(VK_MENU, 0, 0)
    wm.set_foreground_window(mp_h)
    wm.keybd_event(VK_MENU, 0, 2)
    time.sleep(0.3)
    wm.show_window(mp_h, SW_MAXIMIZE)
    time.sleep(0.8)
    probe("STEP1_COVERED_BY_MAX_MSPAINT")

    # 4. Alt+Tab 切回宿主，立即 + 自愈窗后各探一次
    alt_tab_once()
    time.sleep(0.2)
    probe("STEP2_BACK_NOW")
    time.sleep(1.5)
    probe("STEP3_BACK_1_7S")

    # 5. 第二个完整循环
    alt_tab_once()  # → mspaint
    time.sleep(0.4)
    probe("STEP4_COVERED_AGAIN")
    alt_tab_once()  # → 宿主
    time.sleep(0.2)
    probe("STEP5_BACK2_NOW")
    time.sleep(1.5)
    probe("STEP6_BACK2_1_7S")

    z_dump("FINAL")
    print("REPRO_DONE")
    # 判定：自愈窗后左右格必须命中子窗口（z 序拉回宿主正下方）
    hm2 = wm.host_hwnd()
    ok = False
    if hm2:
        hr = wm.get_window_rect(hm2)
        avail = hr.Right - hr.Left - 4 - 8
        mid_y = (hr.Top + hr.Bottom) // 2
        l = wm.proc_name_of(wm.window_from_point(int(hr.Left + 2 + avail * 0.35), mid_y)).lower()
        r = wm.proc_name_of(wm.window_from_point(int(hr.Left + 2 + avail * 0.75), mid_y)).lower()
        print(f"VERDICT_PROBE LEFT={l} RIGHT={r}")
        ok = l == "notepad" and r == "mspaint"
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
