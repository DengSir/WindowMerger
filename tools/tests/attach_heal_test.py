# -*- coding: utf-8 -*-
"""吸附态自愈与释放还原回归（250ms 维护定时器的黑盒行为）：
  H1 外部把子窗口最大化 → 1s 内拉回格子（EnsureDockedState，子窗口没有"最大化"概念）
  H2 外部摘掉 TOOLWINDOW → 1s 内补回（个别框架会重写样式的自愈）
  H3 外部隐藏子窗口 → 1s 内重新可见（SW_SHOWNA）
  H4 子窗口进程被强杀 → 格子清空（状态栏"右: 空"），宿主不崩、另一侧保留
  H5 释放还原：吸附前矩形逐像素回位 + 外部污染的置顶标记被摘除（Restore 全量语义）
  H6 单侧吸附时交换 → 引用整体搬家（SwapSides 左有右空分支）
用法: uv run tools\\tests\\attach_heal_test.py [--exe 路径]
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
import wm_uia
import uiautomation as auto


def wait_tool(h: int, want: bool, timeout_ms: int = 2000) -> bool:
    return wm.wait_until(lambda: wm.is_toolwindow(h) == want, timeout_ms, 100)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    auto.SetGlobalSearchTimeout(5)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    # ---------- 环境：双侧 CLI 吸附 + 固定布局 ----------
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    wm.save_config({"Ratio": 0.5})
    t1 = Path(tempfile.gettempdir(), "wmah1.txt")
    t1.write_text("attach-heal", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    subprocess.Popen(["mspaint"])
    time.sleep(1.8)
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"], env=wm.host_env())
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)
    hr = wm.get_window_rect(hm)
    nps = wm.main_windows_by_name("Notepad")
    nh = nps[0][1]
    mph = wm.main_windows_by_name("mspaint")[0][1]
    if not (wm.is_toolwindow(nh) and wm.is_toolwindow(mph)):
        print("FAIL_ATTACH")
        return 1
    scale = wm.get_dpi_for_window(hm) / 96.0
    bw, tb, dv, mg = round(2 * scale), round(28 * scale), round(6 * scale), round(7 * scale)
    pane_w = int((hr.width - 2 * bw - dv) * 0.5)
    exp_left = (hr.Left + bw - mg, hr.Top + bw + tb,
                hr.Left + bw + pane_w + mg, hr.Bottom - bw + mg)

    # ---------- H1 外部最大化 → 拉回格子 ----------
    wm.show_window(nh, wm.SW_MAXIMIZE)
    time.sleep(1.2)
    r = wm.get_window_rect(nh)
    dev = sum(abs(v - e) for v, e in zip(r.as_tuple(), exp_left))
    check("H1_UNMAXIMIZE_HEAL", not wm.is_zoomed(nh) and dev <= 14,
          f"zoomed={wm.is_zoomed(nh)} dev={dev}")

    # ---------- H2 外部摘 TOOLWINDOW → 补回 ----------
    wm.set_toolwindow(nh, False)
    check("H2_TOOLWINDOW_HEAL", wait_tool(nh, True, 2000),
          f"tool={wm.is_toolwindow(nh)}")

    # ---------- H3 外部隐藏 → 重新可见 ----------
    wm.show_window(nh, wm.SW_HIDE)
    time.sleep(1.2)
    check("H3_VISIBLE_HEAL", wm.is_window_visible(nh),
          f"vis={wm.is_window_visible(nh)}")

    # ---------- H4 子窗口进程被杀 → 格子清空 ----------
    mp_pid = wm.pid_of(mph)
    wm.force_kill_pid(mp_pid)

    def right_empty() -> bool:
        st = wm_uia.status_text(hm) or ""
        return "右: 空" in st and "左: " in st

    check("H4_CHILD_LOST_PANE_CLEARED", wm.wait_until(right_empty, 3000, 150),
          f"status={wm_uia.status_text(hm)!r}")
    check("H4_HOST_ALIVE", wm.is_window(hm) and wm.is_window_visible(hm))
    check("H4_OTHER_SIDE_KEPT", wm.is_toolwindow(nh))

    # ---------- H5 释放还原：矩形回位 + 摘置顶污染（经 picker 吸附新 mspaint）----------
    mp2 = subprocess.Popen(["mspaint"])
    time.sleep(2.0)
    mp2s = wm.main_windows_by_name("mspaint")
    if not mp2s:
        print("FAIL_NO_MSPAINT2")
        return 1
    mh2 = mp2s[0][1]
    mp_pre = wm.get_window_rect(mh2)
    # picker 吸附到右格（空格）：UIA Invoke → 选中行 → 吸附按钮
    wm_uia.invoke(wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm),
                                               "_pickRightButton"))
    picker = 0

    def find_picker() -> bool:
        nonlocal picker
        for h in wm.all_windows_of_pid(wm.pid_of(hm)):
            if h != hm and "选择吸附到" in wm.get_text(h):
                picker = h
                return True
        return False

    if not wm.wait_until(find_picker, 5000, 200) or not picker:
        print("FAIL_NO_PICKER")
        return 1
    pe = wm_uia.element_from_handle(picker)
    row = None
    for c, _ in auto.WalkControl(pe, includeTop=False, maxDepth=8):
        if c.ControlTypeName in ("ListItemControl", "DataItemControl") \
                and "mspaint" in (c.Name or "").lower():
            row = c
            break
    if row is None:
        print("FAIL_NO_ROW")
        wm_uia.invoke(wm_uia.find_by_name(pe, "取消"))
        return 1
    row.GetSelectionItemPattern().Select()
    time.sleep(0.3)
    wm_uia.invoke(wm_uia.find_by_name(pe, "吸附"))
    time.sleep(1.5)
    check("H5A_PICKER_ATTACH", wm.is_toolwindow(mh2))
    # 吸附态下外部污染置顶，释放必须摘除 + 矩形回吸附前位置
    wm.set_topmost(mh2, True)
    time.sleep(0.3)
    wm_uia.invoke(wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm),
                                               "_releaseButton"))
    time.sleep(1.5)
    r2 = wm.get_window_rect(mh2)
    back = all(abs(v - e) <= 3 for v, e in zip(r2.as_tuple(), mp_pre.as_tuple()))
    check("H5B_RESTORE_RECT", back,
          f"now={r2.as_tuple()} pre={mp_pre.as_tuple()}")
    check("H5C_RESTORE_UNTOPMOST", not wm.is_topmost(mh2),
          f"topmost={wm.is_topmost(mh2)}")
    check("H5D_RELEASE_UNTOOL", not wm.is_toolwindow(mh2))

    # ---------- H6 单侧吸附交换 ----------
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("mspaint")
    subprocess.Popen([a.exe, "--left", "notepad"], env=wm.host_env())
    time.sleep(4)
    hm2 = wm.host_hwnd()
    if not hm2:
        print("NO_HOST2")
        return 1
    wm.set_window_pos(hm2, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm2, True)
    time.sleep(0.4)
    hr2 = wm.get_window_rect(hm2)
    nps2 = wm.main_windows_by_name("Notepad")
    nh2 = nps2[0][1]
    pane_w2 = (hr2.width - 15) // 2
    rcx = hr2.Left + 3 + pane_w2 + 9 + pane_w2 // 2
    lcx = hr2.Left + 3 + pane_w2 // 2
    mid_y = hr2.Top + 45 + (hr2.height - 48) // 2
    wm_uia.invoke(wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm2),
                                               "_swapButton"))
    time.sleep(1.5)
    st = wm_uia.status_text(hm2) or ""
    right_hit = wm.proc_name_of(wm.window_from_point(rcx, mid_y)).lower()
    left_hit = wm.proc_name_of(wm.window_from_point(lcx, mid_y)).lower()
    check("H6_SWAP_SINGLE_SIDE",
          "左: 空" in st and right_hit == "notepad" and wm.is_toolwindow(nh2),
          f"status={st!r} RIGHT_HIT={right_hit} LEFT_HIT={left_hit}")

    wm.set_topmost(hm2, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
