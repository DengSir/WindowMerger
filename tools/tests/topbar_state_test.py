# -*- coding: utf-8 -*-
"""顶条状态回归（WM_GETMINMAXINFO / ShowNotice / 布局按钮 黑盒）：
  T1 最大化矩形 = 所在显示器工作区（不盖任务栏，ptMaxPosition/ptMaxSize 修正）
  T2 最大化态顶条原地单击不还原（armed 未超阈值，TopBarOnMouseDown 原地点击语义）
  T3 空吸附点"快捷方式" → 状态栏"未吸附窗口：先吸附再创建快捷方式"，桌面无新增 .lnk
  T4 吸附后：布局按钮存在（f0db）、左格提示折叠（UIA IsOffscreen）、右格提示在屏、
     状态栏"左: 标题 / 右: 空"（多布局后选窗入口 = 点空格，侧按钮已退役）
用法: uv run tools\\tests\\topbar_state_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad；不在桌面留 .lnk。
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    wm.force_kill_by_name("WindowMerger", "Notepad")
    time.sleep(0.8)
    wm.remove_config()
    wm.save_config({"Ratio": 0.5})

    # ---------- 阶段 1：空宿主 ----------
    subprocess.Popen([a.exe], env=wm.host_env())
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    pin = wm.test_layout()["host"]
    wm.set_window_pos(hm, None, *pin, wm.SWP_NOZORDER)
    time.sleep(1.0)
    wm.set_topmost(hm, True)
    time.sleep(0.3)
    hr = wm.get_window_rect(hm)

    # T1 最大化矩形 = 工作区
    wm.show_window(hm, wm.SW_MAXIMIZE)
    time.sleep(1.0)
    rmax = wm.get_window_rect(hm)
    wa = wm.pick_test_monitor().rcWork
    t1_ok = (abs(rmax.Left - wa.Left) <= 2 and abs(rmax.Top - wa.Top) <= 2
             and abs(rmax.Right - wa.Right) <= 2 and abs(rmax.Bottom - wa.Bottom) <= 2)
    check("T1_MAX_RECT_IS_WORKAREA", t1_ok,
          f"max=({rmax.Left},{rmax.Top})-({rmax.Right},{rmax.Bottom}) "
          f"wa=({wa.Left},{wa.Top})-({wa.Right},{wa.Bottom})")

    # T2 最大化态原地单击不还原（位移 0）。顶条自动隐藏（触顶唤出，issue #1）：
    # 只有贴住窗口最上沿才滑入——条内中部不再触发（隐藏期顶条带是透明穿透区，
    # 停在那儿直接单击会落空）；触顶等轮询滑入后在原地单击（armed 未超阈值）
    cx, cy = hr.Left + int(hr.width * 0.3), rmax.Top + 2
    wm.set_cursor_pos(cx, cy)
    time.sleep(0.5)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.06)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(0.8)
    check("T2_CLICK_KEEPS_MAXIMIZED", wm.is_zoomed(hm))
    wm.show_window(hm, wm.SW_RESTORE)
    time.sleep(1.0)

    # T3 已随快捷方式按钮退役（merge 子命令一并退役，无 .lnk 生成面）

    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)

    # ---------- 阶段 2：选择器吸附 notepad → 侧按钮字形翻转 ----------
    t1f = Path(tempfile.gettempdir(), "wmts1.txt")
    t1f.write_text("topbar-state", encoding="ascii")
    subprocess.Popen(["notepad", str(t1f)])
    if not wm.wait_main_windows("Notepad"):
        print("FAIL_TARGET_NOT_RUNNING")
        return 1
    subprocess.Popen([a.exe], env=wm.host_env())
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.0)
    if not wm_uia.attach_via_panes(hm, [(0, "notepad")]):
        print("FAIL_PICKER_ATTACH")
        return 1
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)
    el = wm_uia.element_from_handle(hm)
    lb = wm_uia.find_by_automation_id(el, "_layoutLrButton")
    check("T4_LAYOUT_BUTTON_PRESENT", lb is not None and wm_uia.name_of(lb) == "\uEE4D",
          f"name={wm_uia.name_of(lb)!r}")
    hint0 = wm_uia.find_by_automation_id(el, "_paneHint0")
    hint1 = wm_uia.find_by_automation_id(el, "_paneHint1")
    # 占用格提示折叠：WPF peer 仍留在 UIA 树但 IsOffscreen=True（不是从树里消失）；
    # 空格提示在场且在屏上（Invoke 可达）
    def offscreen(e) -> bool:
        try:
            return bool(e.IsOffscreen)
        except Exception:
            return True

    check("T4_HINT0_OFFSCREEN_WHEN_OCCUPIED", hint0 is None or offscreen(hint0),
          f"hint0={hint0}")
    check("T4_HINT1_ONSCREEN_WHEN_EMPTY", hint1 is not None and not offscreen(hint1),
          f"hint1={hint1}")
    st = wm_uia.status_text(hm) or ""
    check("T4_STATUS_PER_PANE", "右: 空" in st and "左: " in st, f"status={st!r}")
    hr = wm.get_window_rect(hm)
    pane_w = (hr.width - 15) // 2
    mid_y = hr.Top + 45 + (hr.height - 48) // 2
    l = wm.proc_name_of(wm.window_from_point(hr.Left + 3 + pane_w // 2, mid_y)).lower()
    r = wm.proc_name_of(wm.window_from_point(hr.Left + 3 + pane_w + 9 + pane_w // 2, mid_y)).lower()
    check("T4_PANE_HITS", l == "notepad" and r != "notepad", f"LEFT_HIT={l} RIGHT_HIT={r}")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad")
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
