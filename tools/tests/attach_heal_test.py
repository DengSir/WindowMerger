# -*- coding: utf-8 -*-
r"""吸附态自愈与释放还原回归（250ms 维护定时器的黑盒行为）：
  H1 外部把子窗口最大化 → 1s 内拉回格子（EnsureDockedState，子窗口没有"最大化"概念）
  H2 外部重新收录任务栏 → 低频重断言再隐藏（DeleteTab 方案的 shell 侧自愈，
     覆盖 explorer 重启重建 task list 的场景）
  H4 子窗口进程被强杀 → 格子清空（状态栏"右: 空"），宿主不崩、另一侧保留
  H5 释放还原：吸附前矩形逐像素回位 + 外部污染的置顶标记被摘除（Restore 全量语义）
  H6 单侧吸附时交换 → 引用整体搬家（SwapSides 左有右空分支）
  H7 外部隐藏吸附子窗口（任意来源）→ 不拉回，自动释放还原（Undock + 回吸附前矩形 +
     保持隐藏）。旧 H3"外部隐藏 → SW_SHOWNA 拉回可见"已废弃：应用自行隐藏 = 关闭/
     托盘意图，强制拉回只会造出不响应不重绘的僵尸窗
  H8 真托盘链路：tray_target 靶窗收到 WM_CLOSE 自己隐藏（微信类"关闭到托盘"行为，
     隐藏由靶窗自己的关闭处理发起，区别于 H7 的外部 SW_HIDE）→ 同样释放还原；
     托盘唤回（ShowWindow 模拟）后任务栏按钮回归
吸附态探针 = 圆角直角化（corner_pref==1，吸附流程唯一写入者），不再是 TOOLWINDOW 样式。
用法: uv run tools/tests/attach_heal_test.py [--exe 路径]
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
    subprocess.Popen(["mspaint"])
    if not wm.wait_main_windows("Notepad", "mspaint"):
        print("FAIL_TARGETS_NOT_RUNNING")
        return 1
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
    if not (wm.is_attached(nh) and wm.is_attached(mph)):
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

    # ---------- H2 外部重新收录任务栏 → 低频重断言再隐藏 ----------
    def notepad_button() -> bool:
        return any("记事本" in n or "notepad" in n.lower() for n in wm_uia.dump_taskbar_buttons())

    wm.taskbar_tab(nh, True)  # 模拟 shell 重新收录（explorer 重启重建 task list 同款）
    time.sleep(0.6)
    btn_back = notepad_button()
    rehidden = wm.wait_until(lambda: not notepad_button(), 5000, 300) if btn_back else False
    check("H2_TAB_REASSERT_REHIDE", btn_back and rehidden, f"btn_back={btn_back}")

    # ---------- H4 子窗口进程被杀 → 格子清空 ----------
    mp_pid = wm.pid_of(mph)
    wm.force_kill_pid(mp_pid)

    def right_empty() -> bool:
        st = wm_uia.status_text(hm) or ""
        return "右: 空" in st and "左: " in st

    check("H4_CHILD_LOST_PANE_CLEARED", wm.wait_until(right_empty, 3000, 150),
          f"status={wm_uia.status_text(hm)!r}")
    check("H4_HOST_ALIVE", wm.is_window(hm) and wm.is_window_visible(hm))
    check("H4_OTHER_SIDE_KEPT", wm.is_attached(nh))

    # ---------- H5 释放还原：矩形回位 + 摘置顶污染（经 picker 吸附新 mspaint）----------
    mp2 = subprocess.Popen(["mspaint"])
    if not wm.wait_main_windows("mspaint"):
        print("FAIL_NO_MSPAINT2")
        return 1
    mh2 = wm.main_windows_by_name("mspaint")[0][1]
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
    check("H5A_PICKER_ATTACH", wm.is_attached(mh2))
    # 吸附态下外部污染置顶，释放必须摘除 + 矩形回吸附前位置
    wm.set_topmost(mh2, True)
    time.sleep(0.3)
    # 用户主动释放 → 被释放窗口拉回前台：UIA Invoke 不改前台，宿主须先持前台
    # （SetForegroundWindow 转交仅在前台锁规则内成立），释放后断言前台 = mspaint
    wm.set_foreground_window(hm)
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
    check("H5D_RELEASE_UNTOOL", not wm.is_attached(mh2))
    fg = wm.get_foreground_window()
    check("H5E_RELEASE_FOREGROUND", fg == mh2,
          f"fg={fg}({wm.proc_name_of(fg) if fg else None}) expect={mh2}")

    # ---------- H6 单侧吸附交换 ----------
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("mspaint")
    nh2_pre = wm.get_window_rect(nh)  # host2 吸附前矩形：优雅关闭已把 notepad 还原回原位
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
          "左: 空" in st and right_hit == "notepad" and wm.is_attached(nh2),
          f"status={st!r} RIGHT_HIT={right_hit} LEFT_HIT={left_hit}")

    # ---------- H7 子窗口自行隐藏（关闭/最小化到托盘类应用）→ 不拉回，自动释放 ----------
    wm.show_window(nh2, wm.SW_HIDE)
    time.sleep(1.2)
    released = wm.wait_until(lambda: "已自行隐藏" in (wm_uia.status_text(hm2) or ""), 4000, 150)
    check("H7_SELFHIDE_RELEASE_NOTICE", released,
          f"status={wm_uia.status_text(hm2)!r}")
    check("H7_NOT_FORCED_VISIBLE", wm.is_window(nh2) and not wm.is_window_visible(nh2),
          f"alive={wm.is_window(nh2)} vis={wm.is_window_visible(nh2)}")
    check("H7_UNDOCKED", not wm.is_attached(nh2))
    # 隐藏态无任务栏按钮是 shell 对隐藏窗口的正常表现（托盘应用外观）——AddTab 已在
    # 释放时执行，tab 态无查询接口，黑盒只能验"重新显示后按钮回归"（DeleteTab 残留
    # 不加回 = 孤儿症状；隐藏期 AddTab 注册必须存续）
    wm.show_window(nh2, wm.SW_SHOWNA)
    btn_back2 = wm.wait_until(notepad_button, 3000, 200)
    check("H7_TASKBAR_AFTER_RESHOW", btn_back2 and wm.is_window_visible(nh2) and not wm.is_attached(nh2),
          f"btn={btn_back2} vis={wm.is_window_visible(nh2)} attached={wm.is_attached(nh2)}")
    r7 = wm.get_window_rect(nh2)
    back7 = all(abs(v - e) <= 3 for v, e in zip(r7.as_tuple(), nh2_pre.as_tuple()))
    check("H7_RECT_RESTORED", back7, f"now={r7.as_tuple()} pre={nh2_pre.as_tuple()}")
    # 通知 3 秒驻留结束后双侧皆空 → 状态栏回到空格占位提示
    cleared = wm.wait_until(lambda: "把任意窗口拖进来吸附" in (wm_uia.status_text(hm2) or ""), 5000, 200)
    check("H7_PANE_CLEARED", cleared, f"status={wm_uia.status_text(hm2)!r}")

    # ---------- H8 真托盘链路：靶窗收到 WM_CLOSE 自隐藏（关闭到托盘类应用）→ 释放 ----------
    tray = subprocess.Popen([sys.executable,
                             str(Path(__file__).resolve().parents[1] / "targets" / "tray_target.py")],
                            creationflags=0x08000000)
    th = 0
    for _ in range(25):
        th = wm.find_window_by_title("WM_TRAY_TARGET")
        if th:
            break
        time.sleep(0.2)
    if not th:
        print("FAIL_NO_TRAY_TARGET")
        tray.kill()
        return 1
    tray_pid = wm.pid_of(th)
    tray_pre = wm.get_window_rect(th)
    # 宿主运行中没有运行时吸附入口，重启带 --left PID 精确吸附（H6 同款模式）
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    subprocess.Popen([a.exe, "--left", str(tray_pid)], env=wm.host_env())
    time.sleep(4)
    hm3 = wm.host_hwnd()
    if not hm3:
        print("NO_HOST3")
        tray.kill()
        return 1
    wm.set_window_pos(hm3, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm3, True)
    time.sleep(0.4)
    if not wm.is_attached(th):
        print("FAIL_TRAY_ATTACH")
        tray.kill()
        return 1
    # 点 X（等价）：向靶窗投递 WM_CLOSE → 靶窗自己的关闭处理隐藏自己（进程存活）
    wm.post_close(th)
    time.sleep(1.2)
    released8 = wm.wait_until(lambda: "已自行隐藏" in (wm_uia.status_text(hm3) or ""), 4000, 150)
    check("H8_TRAY_CLOSE_RELEASE_NOTICE", released8,
          f"status={wm_uia.status_text(hm3)!r}")
    check("H8_TRAY_NOT_FORCED_VISIBLE", wm.is_window(th) and not wm.is_window_visible(th),
          f"alive={wm.is_window(th)} vis={wm.is_window_visible(th)}")
    check("H8_TRAY_UNDOCKED", not wm.is_attached(th))
    r8 = wm.get_window_rect(th)
    back8 = all(abs(v - e) <= 3 for v, e in zip(r8.as_tuple(), tray_pre.as_tuple()))
    check("H8_TRAY_RECT_RESTORED", back8, f"now={r8.as_tuple()} pre={tray_pre.as_tuple()}")
    cleared8 = wm.wait_until(lambda: "把任意窗口拖进来吸附" in (wm_uia.status_text(hm3) or ""), 5000, 200)
    check("H8_TRAY_PANE_CLEARED", cleared8, f"status={wm_uia.status_text(hm3)!r}")
    # 用户点托盘图标唤回（ShowWindow 模拟）：任务栏按钮回归（AddTab 注册存续）+ 仍脱离吸附
    wm.show_window(th, wm.SW_SHOWNA)
    btn8 = wm.wait_until(lambda: any("python" in n.lower() for n in wm_uia.dump_taskbar_buttons()),
                         3000, 200)
    check("H8_TRAY_TASKBAR_AFTER_RESHOW", btn8 and wm.is_window_visible(th) and not wm.is_attached(th),
          f"btn={btn8} vis={wm.is_window_visible(th)} attached={wm.is_attached(th)}")

    wm.set_topmost(hm2, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    tray.kill()
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
