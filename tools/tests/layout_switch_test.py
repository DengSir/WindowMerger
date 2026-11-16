# -*- coding: utf-8 -*-
"""多布局回归（PaneLayout 引擎 / 布局切换迁移 / 空格点击选窗 / 持久化）：
  L1 config 驱动四布局逐格命中探针（LR/LCR/LTR/Quad）：每格中心 WindowFromPoint = 宿主
     （空格提示填充，几何公式与 src/PaneLayout.cs 同式复算）
  L2 布局按钮直切（UIA Invoke _layoutLtrButton，原下拉菜单退役）：LR→LTR 迁移——左窗留左格、
     右窗按重叠进右上格；config.Layout 即时落盘跟随；状态栏按格名更新
  L3 LTR 下 Invoke _paneHint2（右下格空格提示）→ 选择器标题带格名【右下】（每格独立入口）
  L4 切回 LR：右上格窗口按重叠迁移回右格（左窗不动），落盘 Layout==LR
用法: uv run tools\\tests\\layout_switch_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

BW, TOPBAR, DV = 2.0, 28.0, 6.0  # 布局常量（与 XAML/PaneLayout 同源值）


def pane_probes(kind: str, hr, scale: float) -> dict:
    """各格中心（设备像素）——与 PaneLayout.PaneRects 同式复算，r1=r2=0.5。"""
    x0 = hr.Left + BW * scale
    y0 = hr.Top + (BW + TOPBAR) * scale
    cw = hr.width - (2 * BW + (2 if kind == "LCR" else 1) * DV) * scale
    ch = hr.height - (2 * BW + (1 if kind in ("LTR", "Quad") else 0) * DV + TOPBAR) * scale
    avail_h = ch - (DV * scale if kind in ("LTR", "Quad") else 0)
    half = DV * scale / 2
    cy_mid = y0 + ch / 2
    p = {}
    if kind == "LR":
        p["左"] = (x0 + cw * 0.25, cy_mid)
        p["右"] = (x0 + cw * 0.5 + DV * scale + cw * 0.25, cy_mid)
    elif kind == "LCR":
        p["左"] = (x0 + cw * 0.125, cy_mid)
        p["中"] = (x0 + cw * 0.5 + DV * scale + cw * 0.125, cy_mid)
        p["右"] = (x0 + cw * 0.75 + 2 * DV * scale + cw * 0.125, cy_mid)
    elif kind == "LTR":
        cx_right = x0 + cw * 0.5 + DV * scale + cw * 0.25
        p["左"] = (x0 + cw * 0.25, y0 + ch / 2)
        p["右上"] = (cx_right, y0 + avail_h * 0.25)
        p["右下"] = (cx_right, y0 + avail_h * 0.5 + DV * scale + avail_h * 0.25)
    else:  # Quad
        cx_l = x0 + cw * 0.25
        cx_r = x0 + cw * 0.5 + DV * scale + cw * 0.25
        cy_t = y0 + avail_h * 0.25
        cy_b = y0 + avail_h * 0.5 + DV * scale + avail_h * 0.25
        p["左上"] = (cx_l, cy_t)
        p["右上"] = (cx_r, cy_t)
        p["左下"] = (cx_l, cy_b)
        p["右下"] = (cx_r, cy_b)
    # 避开分隔条半宽（探针理论上不会落在条上，防御性收一点）
    return {k: (int(x), int(y)) for k, (x, y) in p.items()}


def hit_proc(x: int, y: int) -> str:
    return wm.proc_name_of(wm.window_from_point(x, y)).lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    def switch_layout_by_button(hm: int, automation_id: str) -> bool:
        """Invoke 直排布局按钮，点按即切（2026-11-16 下拉菜单退役，换四按钮
        _layoutLr/Lcr/Ltr/QuadButton：字形 EE4D / EA4B+EA4C 叠加 / EE4E / EE4F）。"""
        btn = wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm), automation_id)
        if btn is None:
            print(f"LAYOUT_BUTTON_NOT_FOUND id={automation_id}")
            return False
        wm_uia.invoke(btn)
        time.sleep(1.2)
        return True

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.5)

    # ---------- L1 四布局逐格命中（空宿主：每格中心 = 宿主自身提示填充） ----------
    for kind in ("LR", "LCR", "LTR", "Quad"):
        wm.remove_config()
        wm.save_config({"Layout": kind})
        subprocess.Popen([a.exe], env=wm.host_env())
        time.sleep(4)
        hm = wm.host_hwnd()
        if not hm:
            check(f"L1_{kind}_HOST", False)
            continue
        wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
        time.sleep(1.0)
        wm.set_topmost(hm, True)
        time.sleep(0.3)
        hr = wm.get_window_rect(hm)
        scale = wm.get_dpi_for_window(hm) / 96.0
        probes = pane_probes(kind, hr, scale)
        hits = {name: hit_proc(x, y) for name, (x, y) in probes.items()}
        ok = all(v == "windowmerger" for v in hits.values())
        check(f"L1_{kind}_PANE_PROBES", ok, f"hits={hits}")
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.5)

    # ---------- L2-L4 吸附两窗 + 菜单切换 ----------
    wm.remove_config()
    wm.save_config({"Layout": "LR"})
    subprocess.Popen(["notepad"])
    subprocess.Popen(["mspaint"])
    if not wm.wait_main_windows("Notepad", "mspaint"):
        print("FAIL_TARGETS_NOT_RUNNING")
        return 1
    subprocess.Popen([a.exe, "merge", "--left", "notepad", "--right", "mspaint"],
                     env=wm.host_env())
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.3)
    nps = wm.main_windows_by_name("Notepad")[0][1]
    mph = wm.main_windows_by_name("mspaint")[0][1]
    hr = wm.get_window_rect(hm)
    scale = wm.get_dpi_for_window(hm) / 96.0

    if not switch_layout_by_button(hm, "_layoutLtrButton"):
        check("L2_BUTTON_SWITCH_LTR", False)
    else:
        check("L2_BUTTON_SWITCH_LTR", True)
        cfg = wm.load_config()
        check("L2_CONFIG_LTR", cfg.get("Layout") == "LTR", f"cfg={cfg.get('Layout')}")
        probes = pane_probes("LTR", wm.get_window_rect(hm), scale)
        # 重叠迁移：左窗留左格、右窗（右半全高矩形）与右上/右下并列取低索引 → 右上
        l = hit_proc(*probes["左"])
        rt = hit_proc(*probes["右上"])
        check("L2_MIGRATE_KEEP_LEFT", wm.is_attached(nps) and l == "notepad", f"LEFT_HIT={l}")
        check("L2_MIGRATE_RIGHT_TO_TOPRIGHT", wm.is_attached(mph) and rt == "mspaint",
              f"TOPRIGHT_HIT={rt}")
        st = wm_uia.status_text(hm) or ""
        check("L2_STATUS_PANE_NAMES", "右上: " in st and "右下: 空" in st, f"status={st!r}")

    # ---------- L3 空格提示按钮 = 每格独立选窗入口（右下格） ----------
    hint2 = wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm), "_paneHint2")
    if hint2 is None:
        check("L3_HINT2_PRESENT", False)
    else:
        wm_uia.invoke(hint2)
        picker = 0

        def find_picker() -> bool:
            nonlocal picker
            for h in wm.all_windows_of_pid(wm.pid_of(hm)):
                if h != hm and "选择吸附到" in wm.get_text(h):
                    picker = h
                    return True
            return False

        found = wm.wait_until(find_picker, 5000, 200)
        title = wm.get_text(picker) if picker else ""
        check("L3_PANE_PICKER_TITLE", bool(found) and "右下" in title, f"title={title!r}")
        if picker:
            wm.post_close(picker)
            time.sleep(1.0)

    # ---------- L4 切回 LR：右上格窗口按重叠迁回右格 ----------
    if switch_layout_by_button(hm, "_layoutLrButton"):
        cfg = wm.load_config()
        check("L4_CONFIG_LR", cfg.get("Layout") == "LR", f"cfg={cfg.get('Layout')}")
        probes = pane_probes("LR", wm.get_window_rect(hm), scale)
        l = hit_proc(*probes["左"])
        r = hit_proc(*probes["右"])
        check("L4_MIGRATE_BACK", wm.is_attached(nps) and wm.is_attached(mph)
              and l == "notepad" and r == "mspaint", f"LEFT_HIT={l} RIGHT_HIT={r}")
    else:
        check("L4_BUTTON_SWITCH_LR", False)

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("Notepad", "mspaint")
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
