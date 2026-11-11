# -*- coding: utf-8 -*-
"""光标落点判定回归（注入拖动，**固定布局**——除恢复定位测试外所有拖动测试的约定）：
宿主与 mspaint 先 SetWindowPos 钉到主屏固定矩形（主屏上 app 坐标==物理坐标，无跨 DPI
换算；mspaint 做拖动靶——Win11 notepad 自我缩放/最小尺寸钳制不可靠，用户确认）：
CASE B 拖到宿主上方外侧松手（光标在外、窗口中心落进左格）→ 必须不吸附——旧中心逻辑会误吸；
CASE A 再从那里拖到左格中心 → 必须吸附。
原 CursorDropTest.ps1；旧版 notepad+动态坐标在多屏混合 DPI 下失效（2026-11 实测）。
用法: uv run tools/\tests\\cursor_drop_test.py [--exe 路径]
判定: CASE_B tool=False 且 CASE_A tool=True + LEFT_HIT=mspaint → exit 0。
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json（比例/几何复位 0.5/默认）。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

# 固定布局（wm.test_layout() 按工作区自适应：4K 开发机 / CI 1920 屏两套）
HOST_RECT = wm.test_layout()["host"]   # 大屏左格物理宽 ≈1092 ≥ mspaint 最小宽 1056
MP_RECT = wm.test_layout()["target"]   # mspaint 靶窗（PMv2 会被按 DPI 放大，以回读为准）


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


def focus_and_check(grab_x: int, grab_y: int, hwnd: int) -> bool:
    """ALT 技巧置前台后确认抓点命中 mspaint（被盖时注入不可靠 → 放弃）。"""
    for _ in range(3):
        wm.keybd_event(0x12, 0, 0)
        wm.set_foreground_window(hwnd)
        wm.keybd_event(0x12, 0, 2)
        time.sleep(0.4)
        if wm.proc_name_of(wm.window_from_point(grab_x, grab_y)).lower() == "mspaint":
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 1. 全新环境（删 config → 比例 0.5、几何默认）
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

    # 2. 钳位：宿主 + mspaint 固定矩形（物理坐标；钳位基准 = 测试显示器工作区，
    #    宿主可能停在 96 DPI 副屏——SM_CYSCREEN 的主屏高与它无关）
    hx, hy, hw, hh = HOST_RECT
    mx, my, mw, mh2 = MP_RECT
    wa = wm.pick_test_monitor().rcWork
    if my + mh2 > wa.Bottom - 10:
        my = wa.Bottom - mh2 - 10  # 矮工作区放不下时上移，钉位矩形整体留在屏内
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.0)  # 维护定时器收敛
    wm.set_window_pos(mh, None, mx, my, mw, mh2, wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
    time.sleep(0.5)
    hr = wm.get_window_rect(hm)
    r = wm.get_window_rect(mh)
    print(f"HOST pinned ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")
    print(f"MSPAINT pinned ({r.Left},{r.Top})-({r.Right},{r.Bottom})")

    # 左格矩形（物理 px）：x hx+3 .. hx+3+(hw-15)/2，y hy+45 .. hy+hh-3
    pane_l, pane_t = hx + 3, hy + 45
    pane_r = hx + 3 + (hw - 15) // 2
    pane_b = hy + hh - 3
    pane_cx, pane_cy = (pane_l + pane_r) // 2, (pane_t + pane_b) // 2

    # 3. CASE B：拖标题栏中点，光标停在宿主上方外侧。抓点 x = 窗口中线 →
    #    光标 x 即松手后中心 x；抓点 = wm.title_grab_point()（WM_NCHITTEST 探测
    #    真实 HTCAPTION，几何推算无通用解——商店画图顶部 ~8px 是缩放热区）
    grab_x, grab_y = wm.title_grab_point(mh)
    if not focus_and_check(grab_x, grab_y, mh):
        print("SKIP_COVERED")
        return 1
    half_w, half_h = r.width // 2, r.height // 2
    target_cx, _ = wm.test_layout()["drop_center"]
    # 光标 y 直接构造为宿主上沿外 10px，中心 y = cur_y + half_h - 抓点dy 随之落进左格：
    # 远端公式 target_cy + 抓点dy - half_h 隐含"半高 > 目标中心距"假设，靶窗半高不足时
    # 光标落进宿主内构造不成立（本机 Paint 11.2605 接受 620px 钉位高度不钳制，实测）
    cur_x = target_cx
    cur_y = hr.Top - 10
    print(f"CASE_B release cursor=({cur_x},{cur_y}) outsideHost={cur_y < hr.Top}")
    drag(grab_x, grab_y, cur_x, cur_y)
    r = wm.get_window_rect(mh)
    cx, cy = (r.Left + r.Right) // 2, (r.Top + r.Bottom) // 2
    in_left_pane = pane_l < cx < pane_r and pane_t < cy < pane_b
    case_b_ok = not wm.is_attached(mh)
    print(f"CASE_B_NO_ATTACH_EXPECTED: tool={wm.is_attached(mh)} "
          f"rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) center=({cx},{cy}) "
          f"centerInLeftPane={in_left_pane} (构造须成立)")

    # 4. CASE A：从新位置抓标题栏中点拖到左格中心 → 必须吸附
    grab_x, grab_y = wm.title_grab_point(mh)
    if not focus_and_check(grab_x, grab_y, mh):
        print("SKIP_CASE_A_COVERED")
        return 1
    drag(grab_x, grab_y, pane_cx, pane_cy)
    r2 = wm.get_window_rect(mh)
    case_a_ok = wm.is_attached(mh)
    print(f"CASE_A_ATTACH_EXPECTED: tool={wm.is_attached(mh)} "
          f"rect=({r2.Left},{r2.Top})-({r2.Right},{r2.Bottom})")
    left_hit = wm.proc_name_of(wm.window_from_point(pane_cx, pane_cy)).lower()
    print(f"LEFT_HIT={left_hit}")
    hit_ok = left_hit == "mspaint"

    # 5. 清理
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("mspaint")
    print("CURSOR_DROP_TEST_DONE")
    ok = case_b_ok and in_left_pane and case_a_ok and hit_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
