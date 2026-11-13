# -*- coding: utf-8 -*-
"""顶条状态回归（WM_GETMINMAXINFO / ShowNotice / UpdateSideButtons 黑盒）：
  T1 最大化矩形 = 所在显示器工作区（不盖任务栏，ptMaxPosition/ptMaxSize 修正）
  T2 最大化态顶条原地单击不还原（armed 未超阈值，TopBarOnMouseDown 原地点击语义）
  T3 空吸附点"快捷方式" → 状态栏"未吸附窗口：先吸附再创建快捷方式"，桌面无新增 .lnk
  T4 吸附后侧按钮字形翻转 f060→f08b（左释放 ScaleX 镜像）、tooltip 换"释放…"（UpdateSideButtons）
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

EMPTY_HINT = "把任意窗口拖进来吸附"


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

    # T2 最大化态原地单击不还原（位移 0）。顶条自动隐藏（移入显示）：入带后等轮询滑入
    scale = wm.get_dpi_for_window(hm) / 96.0
    cx, cy = hr.Left + int(hr.width * 0.3), rmax.Top + round(14 * scale)
    wm.set_cursor_pos(cx, cy)
    time.sleep(0.5)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.06)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(0.8)
    check("T2_CLICK_KEEPS_MAXIMIZED", wm.is_zoomed(hm))
    wm.show_window(hm, wm.SW_RESTORE)
    time.sleep(1.0)

    # T3 空吸附创建快捷方式 → 通知 + 无 .lnk
    desktop = Path(wm.desktop_dir())
    before = sorted(p.name for p in desktop.glob("*.lnk"))
    wm_uia.invoke(wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm),
                                               "_shortcutButton"))
    time.sleep(0.8)
    st = wm_uia.status_text(hm) or ""
    after = sorted(p.name for p in desktop.glob("*.lnk"))
    check("T3_EMPTY_SHORTCUT_NOTICE", "未吸附窗口：先吸附再创建快捷方式" in st,
          f"status={st!r}")
    check("T3_NO_LNK_CREATED", before == after, f"before={len(before)} after={len(after)}")

    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)

    # ---------- 阶段 2：CLI 吸附 notepad → 侧按钮字形翻转 ----------
    t1f = Path(tempfile.gettempdir(), "wmts1.txt")
    t1f.write_text("topbar-state", encoding="ascii")
    subprocess.Popen(["notepad", str(t1f)])
    if not wm.wait_main_windows("Notepad"):
        print("FAIL_TARGET_NOT_RUNNING")
        return 1
    subprocess.Popen([a.exe, "--left", "notepad"], env=wm.host_env())
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST_2")
        return 1
    wm.set_window_pos(hm, None, *pin, wm.SWP_NOZORDER)
    time.sleep(1.5)
    el = wm_uia.element_from_handle(hm)
    bl = wm_uia.find_by_automation_id(el, "_pickLeftButton")
    br = wm_uia.find_by_automation_id(el, "_pickRightButton")
    check("T4_LEFT_GLYPH_RELEASE", bl is not None and wm_uia.name_of(bl) == "\uF08B",
          f"name={wm_uia.name_of(bl)!r}")
    check("T4_RIGHT_GLYPH_STILL_PICK", br is not None and wm_uia.name_of(br) == "\uF061",
          f"name={wm_uia.name_of(br)!r}")
    check("T4_LEFT_TOOLTIP_RELEASE", bl is not None and "释放左窗" in wm_uia.help_text_of(bl),
          f"help={wm_uia.help_text_of(bl)!r}")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad")
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
