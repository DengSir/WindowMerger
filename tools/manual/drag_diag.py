# -*- coding: utf-8 -*-
"""pane_drag D2/D3 拖动诊断：逐步打印矩形/命中/前台，定位注入拖动失效点。"""
import ctypes
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

_user32 = ctypes.windll.user32
VK_CONTROL, KEYEVENTF_KEYUP = 0x11, 0x2
WM_NCLBUTTONDOWN, HTCAPTION = 0xA1, 2


def rect_of(h):
    r = wm.get_window_rect(h)
    return f"({r.Left},{r.Top})-({r.Right},{r.Bottom})"


def main() -> int:
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    wm.save_config({"Ratio": 0.5})
    t1 = Path(tempfile.gettempdir(), "wmdd.txt")
    t1.write_text("diag", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    subprocess.Popen(["mspaint"])
    time.sleep(1.8)
    subprocess.Popen([wm.exe_path(), "--left", "notepad"])
    time.sleep(4)
    hm = wm.host_hwnd()
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)
    hr = wm.get_window_rect(hm)
    mh = wm.main_windows_by_name("mspaint")[0][1]
    print(f"HOST {rect_of(hm)}  MP {rect_of(mh)}")

    pane_w = (hr.width - 15) // 2
    drop_x = hr.Left + 3 + pane_w // 2
    drop_y = hr.Top + 45 + (hr.height - 48) // 2 + 60

    # --- 步骤 1：ALT 置前 + 探抓点 ---
    for _ in range(3):
        wm.keybd_event(0x12, 0, 0)
        wm.set_foreground_window(mh)
        wm.keybd_event(0x12, 0, KEYEVENTF_KEYUP)
        time.sleep(0.4)
        gx, gy = wm.title_grab_point(mh)
        hit = wm.proc_name_of(wm.window_from_point(gx, gy)).lower()
        if hit == "mspaint":
            break
    fg = wm.get_foreground_window()
    print(f"GRAB=({gx},{gy}) probe_hit={hit} fg={wm.proc_name_of(fg)}({fg:X}) mp_hwnd={mh:X}")
    print(f"MP before drag {rect_of(mh)}")

    # --- 步骤 2：真实拖动到 drop 点，中途读矩形 ---
    wm.set_cursor_pos(gx, gy)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, 11):
        wm.set_cursor_pos(gx + int((drop_x - gx) * i / 10), gy + int((drop_y - gy) * i / 10))
        time.sleep(0.025)
    print(f"MP mid-drag   {rect_of(mh)}")
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.0)
    print(f"MP after drop {rect_of(mh)}  tool={wm.is_toolwindow(mh)} "
          f"drop=({drop_x},{drop_y})")

    # --- 步骤 3：PostMessage 拖动（宿主前台 + Ctrl）---
    wm.keybd_event(0x12, 0, 0)
    wm.set_foreground_window(hm)
    wm.keybd_event(0x12, 0, KEYEVENTF_KEYUP)
    time.sleep(0.4)
    print(f"fg after ALT+setFG(host) = {wm.proc_name_of(wm.get_foreground_window())}")
    wm.keybd_event(VK_CONTROL, 0, 0)
    gx2, gy2 = wm.title_grab_point(mh)
    wm.set_cursor_pos(gx2, gy2)
    time.sleep(0.15)
    lp = ((gy2 & 0xFFFF) << 16) | (gx2 & 0xFFFF)
    _user32.PostMessageW(wintypes.HWND(mh), WM_NCLBUTTONDOWN, wintypes.WPARAM(HTCAPTION),
                         wintypes.LPARAM(lp))
    time.sleep(0.4)
    print(f"MP post-NCLB  {rect_of(mh)}")
    for i in range(1, 11):
        wm.set_cursor_pos(gx2 + int((drop_x - gx2) * i / 10), gy2 + int((drop_y - gy2) * i / 10))
        time.sleep(0.025)
    print(f"MP pm-mid     {rect_of(mh)}")
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.2)
    wm.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP)
    time.sleep(0.5)
    print(f"MP pm-after   {rect_of(mh)}  tool={wm.is_toolwindow(mh)}")

    # --- 步骤 4（变体 E）：PostMessage WM_KEYDOWN 给宿主 + 真实拖动 ---
    wm.keybd_event(0x12, 0, 0)
    wm.set_foreground_window(hm)
    wm.keybd_event(0x12, 0, KEYEVENTF_KEYUP)
    time.sleep(0.4)
    WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
    _user32.PostMessageW(wintypes.HWND(hm), WM_KEYDOWN, wintypes.WPARAM(VK_CONTROL),
                         wintypes.LPARAM(0x001D0001))
    time.sleep(0.2)
    gx3, gy3 = wm.title_grab_point(mh)
    wm.set_cursor_pos(gx3, gy3)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, 11):
        wm.set_cursor_pos(gx3 + int((drop_x - gx3) * i / 10), gy3 + int((drop_y - gy3) * i / 10))
        time.sleep(0.025)
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.2)
    _user32.PostMessageW(wintypes.HWND(hm), WM_KEYUP, wintypes.WPARAM(VK_CONTROL),
                         wintypes.LPARAM(0xC01D0001))
    time.sleep(0.5)
    print(f"MP variantE   {rect_of(mh)}  tool={wm.is_toolwindow(mh)} (True=宿主收到了 posted Ctrl)")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("Notepad", "mspaint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
