# -*- coding: utf-8 -*-
"""顶条选窗吸附回归（PickerWindow 全链路，纯 UIA 不注入输入）：
mspaint 已运行未吸附 → UIA Invoke 顶条 ← 按钮 → 选窗对话框输入过滤 "mspaint" →
选中第一行 → 点【吸附】→ 断言 mspaint 进入左格（TOOLWINDOW + LEFT_HIT）。
固定布局：宿主钉主屏（wm.test_layout() 按工作区自适应）。
用法: uv run tools/\tests\\picker_attach_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import uiautomation as auto

HOST_RECT = wm.test_layout()["host"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    auto.SetGlobalSearchTimeout(5)

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
    pid = wm.pid_of(hm)

    # 固定布局：宿主钉位
    hx, hy, hw, hh = HOST_RECT
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.0)
    pane_cx = hx + 3 + (hw - 15) // 4
    pane_cy = hy + 45 + (hh - 48) // 2

    # UIA Invoke 顶条 ← 按钮（空格=选择左窗）
    main_el = auto.ControlFromHandle(hm)
    btn = main_el.ButtonControl(AutomationId="_pickLeftButton")
    if not btn.Exists(3, 0.5):
        print("NO_PICK_BUTTON")
        return 1
    btn.GetInvokePattern().Invoke()
    time.sleep(1.0)

    # 选窗对话框 = 同 PID 的可见顶层窗口（标题含"选择"）。
    # 定位走 Win32 枚举：UIA root children 会漏掉 ShowDialog 的 owned 窗口（实测）
    picker = None
    for h in wm.all_windows_of_pid(pid):
        if h != hm and "选择" in wm.get_text(h, 48):
            picker = auto.ControlFromHandle(h)
            break
    if picker is None:
        print("NO_PICKER_DIALOG")
        return 1
    print(f"PICKER [{picker.Name}]")

    # 过滤框输入进程名（ValuePattern，不走键盘注入）
    edit = picker.EditControl()
    if not edit.Exists(3, 0.5):
        print("NO_FILTER_BOX")
        return 1
    edit.GetValuePattern().SetValue("mspaint")
    time.sleep(0.5)

    # 选中第一行（WPF ListView 行 = ListItem/DataItem）
    row = None
    for c, _ in auto.WalkControl(picker, includeTop=False, maxDepth=8):
        if c.ControlTypeName in ("ListItemControl", "DataItemControl"):
            row = c
            break
    if row is None:
        print("NO_LIST_ROW")
        return 1
    row.GetSelectionItemPattern().Select()
    time.sleep(0.3)

    # 点【吸附】
    ok_btn = picker.ButtonControl(Name="吸附")
    if not ok_btn.Exists(3, 0.5):
        print("NO_OK_BUTTON")
        return 1
    ok_btn.GetInvokePattern().Invoke()
    time.sleep(1.5)  # 吸附 + 布局收敛

    attached = wm.is_attached(mh)
    left_hit = wm.proc_name_of(wm.window_from_point(pane_cx, pane_cy)).lower()
    r = wm.get_window_rect(mh)
    print(f"ATTACHED={attached} LEFT_HIT={left_hit} "
          f"rect=({r.Left},{r.Top})-({r.Right},{r.Bottom})")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("mspaint")
    print("PICKER_ATTACH_TEST_DONE")
    ok = attached and left_hit == "mspaint"
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
