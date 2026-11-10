# -*- coding: utf-8 -*-
"""分隔条半透明缝差分诊断（第四阶段）：手势进行中场景在动，在场/退场两次截图
必然错位产生全屏假 diff——探针只在**手势结束静止后**跑（此前一轮已证：96 DPI 下
右缘缩放后分隔条分数位置边缘无透明）。本轮：左缘/右缘/角部/最大化还原，每步
静止后 3 轮差分；命中保存现场双帧 PNG。
诊断脚本，不进 run_all。
用法: uv run tools/diag/divider_seam_diff.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import ctypes
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

SNAP_DIR = Path(tempfile.gettempdir()) / "wm_seam_diag"
BW_DIP, TOPBAR_DIP, DIVIDER_DIP = 2, 28, 6
HTLEFT, HTRIGHT = 10, 11


def nchittest_at(hwnd: int, x: int, y: int) -> int:
    WM_NCHITTEST, SMTO_ABORTIFHUNG = 0x0084, 0x0002
    lp = (y & 0xFFFF) << 16 | (x & 0xFFFF)
    res = wintypes.LPARAM()
    if ctypes.windll.user32.SendMessageTimeoutW(wintypes.HWND(hwnd), WM_NCHITTEST, None,
                                                wintypes.LPARAM(lp), SMTO_ABORTIFHUNG, 1000,
                                                ctypes.byref(res)):
        return res.value & 0xFFFF
    return -1


def edge_grab_point(hwnd: int, edge: str) -> tuple[int, int] | None:
    r = wm.ext_frame_bounds(hwnd) or wm.get_window_rect(hwnd)
    y = r.Top + r.height // 2
    want = HTRIGHT if edge == "right" else HTLEFT
    rng = range(r.Right - 2, r.Right - 30, -1) if edge == "right" else range(r.Left + 2, r.Left + 30)
    for x in rng:
        if nchittest_at(hwnd, x, y) == want:
            return (x, y)
    return None


def corner_grab_point(hwnd: int) -> tuple[int, int] | None:
    r = wm.ext_frame_bounds(hwnd) or wm.get_window_rect(hwnd)
    for x in range(r.Right - 2, r.Right - 30, -1):
        for y in range(r.Bottom - 2, r.Bottom - 30, -1):
            if nchittest_at(hwnd, x, y) == 17:  # HTBOTTOMRIGHT
                return (x, y)
    return None


def drag(from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 25, dt: float = 0.04) -> None:
    wm.set_cursor_pos(from_x, from_y)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        wm.set_cursor_pos(from_x + int((to_x - from_x) * i / steps),
                          from_y + int((to_y - from_y) * i / steps))
        time.sleep(dt)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(0.8)


def children_rects() -> tuple:
    l = wm.main_windows_by_name("Notepad")
    m = wm.main_windows_by_name("mspaint")
    lh = l[0][1] if l else 0
    mh = m[0][1] if m else 0
    return (wm.get_window_rect(lh) if lh else None, wm.ext_frame_bounds(lh) if lh else None,
            wm.get_window_rect(mh) if mh else None, wm.ext_frame_bounds(mh) if mh else None)


def divider_x() -> int | None:
    l, lefb, r, refb = children_rects()
    if not lefb or not refb:
        return None
    return (lefb.Right + refb.Left) // 2


def probe_once(hm: int, marker_h: int, tag: str, cycles: int = 3) -> int:
    """静止差分：标记在场/退场各截一帧为 1 轮，跑 cycles 轮，报告 diff>60 的列。"""
    dx = divider_x()
    if dx is None:
        print(f"[{tag}] NO_CHILDREN")
        return 0
    hr = wm.get_window_rect(hm)
    x, y, w, h = dx - 60, hr.Top + TOPBAR_DIP + 40, 120, hr.height - TOPBAR_DIP - 80
    total = 0
    for c in range(cycles):
        img_on = wm.capture_screen(x, y, w, h)
        wm.set_window_pos(marker_h, None, 4000, 4000, 0, 0,
                          wm.SWP_NOSIZE | wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
        time.sleep(0.22)
        img_off = wm.capture_screen(x, y, w, h)
        wm.set_window_pos(marker_h, None, x - 60, y - 20, 0, 0,
                          wm.SWP_NOSIZE | wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
        time.sleep(0.22)
        don, doff = img_on.tobytes(), img_off.tobytes()
        col_max = {}
        for i in range(0, min(len(don), len(doff)), 4):
            if don[i] != doff[i] or don[i + 1] != doff[i + 1] or don[i + 2] != doff[i + 2]:
                d = (abs(don[i] - doff[i]) + abs(don[i + 1] - doff[i + 1])
                     + abs(don[i + 2] - doff[i + 2]))
                if d > 60:  # 滤子窗 acrylic/文本 AA 的 ≤55 级微噪声（前轮实测）
                    cx = x + (i // 4) % w
                    if d > col_max.get(cx, 0):
                        col_max[cx] = d
        if col_max:
            total += len(col_max)
            img_on.save(SNAP_DIR / f"{tag}_on_{c}.png")
            img_off.save(SNAP_DIR / f"{tag}_off_{c}.png")
            print(f"[{tag}] cyc{c} 透明列(绝对x:diff) = {sorted(col_max.items())}")
    if not total:
        print(f"[{tag}] 干净（无 diff>60 列）")
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    SNAP_DIR.mkdir(exist_ok=True)

    hx, hy, hw, hh = 500, 500, 1400, 540
    wa = wm.pick_test_monitor().rcWork

    marker = subprocess.Popen([sys.executable,
                               str(Path(__file__).resolve().parents[1] / "targets" / "color_pad.py"),
                               "--color", "255,0,255", "--geometry",
                               f"{min(wa.Right - wa.Left, hw + 200)}x{min(wa.Bottom - wa.Top, hh + 40)}"
                               f"+{max(wa.Left, hx - 100)}+{max(wa.Top, hy - 20)}"])
    time.sleep(1.2)
    marker_h = wm.find_window_by_title("WM_COLOR_PAD")
    if not marker_h:
        print("NO_MARKER")
        return 1

    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("seam-diff", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)
    wm.set_cursor_pos(hx + 60, hy + 14)
    if divider_x() is None:
        print("NO_CHILDREN")
        return 1

    grand = 0
    print("== P0 基线 ==")
    lw, lefb, rw, refb = children_rects()
    print(f"  gap={refb.Left - lefb.Right} L_wr=({lw.Left},{lw.Right}) L_efb=({lefb.Left},{lefb.Right})")
    grand += probe_once(hm, marker_h, "P0")

    print("== P1 右缘 +81（分隔条 x.5 分数位）==")
    g = edge_grab_point(hm, "right")
    drag(g[0], g[1], g[0] + 81, g[1])
    lw, lefb, rw, refb = children_rects()
    print(f"  gap={refb.Left - lefb.Right}")
    grand += probe_once(hm, marker_h, "P1")

    print("== P2 左缘 +80 ==")
    g = edge_grab_point(hm, "left")
    drag(g[0], g[1], g[0] - 80, g[1])
    lw, lefb, rw, refb = children_rects()
    print(f"  gap={refb.Left - lefb.Right} host_x={wm.get_window_rect(hm).Left}")
    grand += probe_once(hm, marker_h, "P2")

    print("== P3 右下角 +60/+40 ==")
    g = corner_grab_point(hm)
    drag(g[0], g[1], g[0] + 60, g[1] + 40)
    grand += probe_once(hm, marker_h, "P3")

    print("== P4 最大化 → 2s → 还原 ==")
    wm.show_window(hm, wm.SW_MAXIMIZE)
    time.sleep(2)
    wm.show_window(hm, wm.SW_RESTORE)
    time.sleep(1.2)
    grand += probe_once(hm, marker_h, "P4")

    print("== P5 拖分隔条 +60（用户恢复操作后再验）==")
    dx = divider_x()
    drag(dx, wm.get_window_rect(hm).Top + TOPBAR_DIP + 60, dx + 60,
         wm.get_window_rect(hm).Top + TOPBAR_DIP + 60)
    grand += probe_once(hm, marker_h, "P5")

    print(f"==== 总命中列数（diff>60）: {grand} ====")
    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    marker.kill()
    wm.force_kill_by_name("Notepad", "mspaint")
    print("SEAM_DIFF_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
