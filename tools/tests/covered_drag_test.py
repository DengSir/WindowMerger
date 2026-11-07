# -*- coding: utf-8 -*-
"""遮挡格拒收回归（IsCoveredAtCursor，**自动化**——固定布局 + 注入拖动）：
宿主钉主屏 + 右格上放置顶红色遮罩窗（tkinter）→ 注入拖 mspaint：
STEP 1 拖到被遮右格松手 → 必须无高亮不吸附（TOOLWINDOW 不置位）；
STEP 2 拖到空左格松手 → 必须吸附。
原 manual/CoveredDragTest.ps1 为人工两步拖拽；注入拖动在固定布局下可靠（2026-11 实测），
升级为自动回归，manual 原版保留作交互排查工具。
用法: uv run tools/\tests\\covered_drag_test.py [--exe 路径]
判定: STEP1 tool=False 且 STEP2 tool=True + LEFT_HIT=mspaint → exit 0。
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

HOST_RECT = (400, 150, 2200, 900)   # 左格物理宽 ≈1092 ≥ mspaint 最小宽 1056
MP_RECT = (400, 1090, 1100, 620)    # mspaint 钉在宿主正下方
GRAB_Y = 15                         # 标题栏内 y 偏移（x 取标题栏中点）


def drag(from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 20) -> None:
    wm.set_cursor_pos(from_x, from_y)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        wm.set_cursor_pos(from_x + int((to_x - from_x) * i / steps),
                          from_y + int((to_y - from_y) * i / steps))
        time.sleep(0.025)
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    subprocess.Popen(["mspaint"])
    time.sleep(1.8)
    subprocess.Popen([a.exe])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    mps = wm.main_windows_by_name("mspaint")
    if not mps:
        print("NO_MSPAINT")
        return 1
    mh = mps[0][1]

    hx, hy, hw, hh = HOST_RECT
    mx, my, mw, mh2 = MP_RECT
    # 注意：mspaint 标题栏必须在宿主矩形外（抓点检查是裸 WindowFromPoint，抓进宿主
    # 空格会命中宿主 → SKIP_COVERED_GRAB），因此矮屏（高 <1500，如 2560x1440）下
    # 钉位矩形底部必然探出屏幕下缘——纯视觉现象，标题栏在屏内可抓，不影响判定
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.0)
    wm.set_window_pos(mh, None, mx, my, mw, mh2, wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
    time.sleep(0.5)
    hr = wm.get_window_rect(hm)
    r = wm.get_window_rect(mh)
    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom}) "
          f"MSPAINT ({r.Left},{r.Top})-({r.Right},{r.Bottom})")

    # 右格上的置顶遮罩（tkinter 无边框窗）。宿主保持普通层：置顶会把 mspaint 压到
    # 下面导致 STEP2 抓不到（实测）；遮罩自身 topmost 已保证盖住宿主
    import tkinter
    cover = tkinter.Tk()
    cover.overrideredirect(True)
    cover.attributes("-topmost", True)
    cover.configure(bg="firebrick")
    cx = int(hr.Left + hr.width * 0.55)
    cy = int(hr.Top + 60)
    cw = int(hr.width * 0.4)
    ch = int(hr.height - 80)
    cover.geometry(f"{cw}x{ch}+{cx}+{cy}")
    tkinter.Label(cover, text="COVERED RIGHT PANE - drops here must be refused",
                  fg="white", bg="firebrick").pack(expand=True, fill="both")
    cover.update()
    print(f"COVER ({cx},{cy})-({cx + cw},{cy + ch}) over RIGHT pane")

    grab_x, grab_y = r.Left + r.width // 2, r.Top + GRAB_Y
    half_w, half_h = r.width // 2, r.height // 2

    # STEP 1: 松手后窗口中心落进被遮右格（旧中心逻辑会误吸）、光标留在遮罩内（保证遮挡）。
    # 标题栏中点抓取 → 光标 x = 中心 x；光标 y = 中心 y + GRAB_Y - 半高
    if wm.proc_name_of(wm.window_from_point(grab_x, grab_y)).lower() != "mspaint":
        cover.destroy()
        print("SKIP_COVERED_GRAB")
        return 1
    target_cx = cx + cw // 2          # 中心目标（右格内、遮罩 x 范围内）
    target_cy = cy + ch - 200         # 中心目标 y：使光标 y = 目标-450 仍在遮罩内
    cur_x = target_cx
    cur_y = target_cy + GRAB_Y - half_h
    print(f"STEP1 release cursor=({cur_x},{cur_y}) insideCover="
          f"{cx <= cur_x <= cx + cw and cy <= cur_y <= cy + ch}")
    drag(grab_x, grab_y, cur_x, cur_y)
    r1 = wm.get_window_rect(mh)
    c1 = ((r1.Left + r1.Right) // 2, (r1.Top + r1.Bottom) // 2)
    step1_ok = not wm.is_toolwindow(mh)
    print(f"STEP1_COVERED_DROP: tool={wm.is_toolwindow(mh)} center=({c1[0]},{c1[1]}) "
          f"droppedInCoveredPane={cx <= c1[0] <= cx + cw and cy <= c1[1] <= cy + ch} (构造须成立)")

    # STEP 2: 从新位置拖到左格中心 → 必须吸附。
    # 标题栏中点在遮罩下面（mspaint 松手后部分被盖），抓未被遮住的左翼（+80，避开图标）
    grab_x, grab_y = r1.Left + 80, r1.Top + GRAB_Y
    pane_cx = hr.Left + 3 + (hr.width - 15) // 4
    pane_cy = hr.Top + 45 + (hr.height - 48) // 2
    if wm.proc_name_of(wm.window_from_point(grab_x, grab_y)).lower() != "mspaint":
        cover.destroy()
        print("SKIP_CASE2_GRAB")
        return 1
    drag(grab_x, grab_y, pane_cx, pane_cy)
    r2 = wm.get_window_rect(mh)
    step2_ok = wm.is_toolwindow(mh)
    left_hit = wm.proc_name_of(wm.window_from_point(pane_cx, pane_cy)).lower()
    print(f"STEP2_FREE_DROP: tool={wm.is_toolwindow(mh)} LEFT_HIT={left_hit} "
          f"rect=({r2.Left},{r2.Top})-({r2.Right},{r2.Bottom})")

    # 清理：关遮罩、优雅关宿主（释放 mspaint）
    cover.destroy()
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("mspaint")
    print("COVERED_DRAG_TEST_DONE")
    ok = step1_ok and step2_ok and left_hit == "mspaint"
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
