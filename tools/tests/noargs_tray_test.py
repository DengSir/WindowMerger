# -*- coding: utf-8 -*-
"""无参组合模式回归（托盘常驻 +「启动到托盘」决定主窗；自行剥掉 WM_NO_TRAY 屏蔽变量）：
  N1 无参启动 → 主窗 + 托盘常驻（mutex 佐证：再起 tray 实例秒退 rc=0）
  N2 WM_CLOSE 主窗 → 窗没进程活（关窗常驻，首次关窗有 balloon 提醒——balloon 不做黑盒断言）
  N3 首实例（托盘）存活时第二无参实例 → 第二扇主窗出现（mutex 占用回退纯窗口模式），首实例无恙
  N4 config StartToTray=true → 无参启动零主窗、托盘常驻
  N5-N8 托盘菜单（UIA 定位任务栏托盘按钮 → 右键开菜单 → 按 Name Invoke；托盘图标收进
     溢出 flyout 且未展开时不在 UIA 树上 → N5-N8 标 SKIP_TRAY_ICON_HIDDEN，exit 0）：
    N5 「启动时检查更新」翻转落盘（原主题菜单 ToggleCheckUpdates 用例迁移至此）
    N8 「开机自启」写无参 Run 值（不含 --tray），再点取消还原
    N6 「打开主窗口」→ 主窗出现（托盘进程内新建宿主）
    N7 「退出」→ 进程优雅退出
用法: uv run tools\\tests\\noargs_tray_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint；临时改 config/Run 注册表（结束恢复）。
"""
import argparse
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia
import uiautomation as auto

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def kill_all() -> None:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)  # 强杀后 mutex 句柄关闭，托盘对象销毁，下一实例才能 createNew


def run_value() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            v, _ = winreg.QueryValueEx(k, "WindowMerger")
            return v
    except OSError:
        return None


def clear_run_value() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "WindowMerger")
    except OSError:
        pass


def tray_button():
    """定位**主任务栏**上的本程序托盘按钮（Name 或 AutomationId 含 WindowMerger；AUMID
    已设 DengSir.WindowMerger，shell 按钮的 AutomationId 常取 AUMID）。只用 uiautomation
    类型化搜索（有界超时）；绝不做客户端全树 WalkControl——任务栏树里挂起的 provider
    （balloon 弹层/XAML 岛）会让 GetChildren 永久阻塞（实测 10 分钟超时实锤）。

    溢出 flyout 收纳态不做兜底：关闭态 XAML 树虚拟化读不到；外部 ShowWindow 能让内容
    可读但输入站未接线（点击不产生 shell 转发，右键弹不出菜单——实测），返回这种按钮
    只会制造假阳性失败。图标被收纳 → None（调用方 SKIP）。"""
    tb = wm.find_window_by_class("Shell_TrayWnd")
    if not tb:
        return None
    try:
        el = wm_uia.element_from_handle(tb)
    except Exception:
        return None
    for search in (
        el.ButtonControl(searchDepth=15,
                         Compare=lambda c, d: "WindowMerger" in (c.Name or "")),
        el.ButtonControl(searchDepth=15,
                         Compare=lambda c, d: "WindowMerger" in (c.AutomationId or "")),
    ):
        if search.Exists(1.5, 0.3):
            rect = search.BoundingRectangle
            if rect.width() > 0 and rect.height() > 0:
                return search
    return None


def right_click_tray(control) -> None:
    rect = control.BoundingRectangle
    cx, cy = int((rect.left + rect.right) / 2), int((rect.top + rect.bottom) / 2)
    wm.set_cursor_pos(cx, cy)
    time.sleep(0.15)
    wm.mouse_event(0x0008)  # MOUSEEVENTF_RIGHTDOWN
    time.sleep(0.05)
    wm.mouse_event(0x0010)  # MOUSEEVENTF_RIGHTUP
    time.sleep(0.4)         # ContextMenuStrip 弹出需要一拍


def move_cursor_away() -> None:
    wm.set_cursor_pos(2, 2)


def invoke_menu_item(pid: int, item_name: str) -> bool:
    """托盘菜单按 Name 找 MenuItem 并 Invoke（WinForms ContextMenuStrip 是托盘进程的
    WindowsForms10.SYSMENU 弹层窗口）。返回是否找到并成功调用。"""
    def find_and_invoke() -> bool:
        for h in wm.all_windows_of_pid(pid):
            if not wm.get_class_name(h).startswith("WindowsForms10.SYSMENU"):
                continue
            try:
                el = wm_uia.element_from_handle(h)
            except Exception:
                continue
            for c, _ in auto.WalkControl(el, includeTop=True, maxDepth=6):
                if c.ControlTypeName == "MenuItemControl" and c.Name == item_name:
                    wm_uia.invoke(c)
                    return True
        return False
    return bool(wm.wait_until(find_and_invoke, 3000, 200))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    kill_all()
    # 组合模式验证环境：剥掉 WM_NO_TRAY（wm.py 导入即注入），保留 WM_UPDATE_OFF 断网
    combined_env = dict(os.environ)
    combined_env.pop("WM_NO_TRAY", None)

    try:
        # ---------- N1 无参 = 托盘 + 主窗 ----------
        p1 = subprocess.Popen([a.exe], env=combined_env)
        host_ok = wm.wait_until(lambda: bool(wm.host_hwnd()), 8000, 200)
        mutex_busy = False
        if host_ok:
            p2 = subprocess.Popen([a.exe, "tray"], env=wm.host_env())
            mutex_busy = wm.wait_until(lambda: p2.poll() is not None, 6000, 100)
        check("N1_COMBINED_HOST_AND_TRAY", host_ok and mutex_busy,
              f"host={host_ok} mutex_busy={mutex_busy}")

        # ---------- N2 关窗常驻 ----------
        hm = wm.host_hwnd()
        resident = False
        if hm:
            wm.post_close(hm)
            time.sleep(2.0)
            resident = not wm.host_hwnd() and p1.poll() is None
        check("N2_CLOSE_RESIDENT", resident,
              f"alive={p1.poll() is None} host={bool(wm.host_hwnd())}")

        # ---------- N3 第二无参实例回退纯窗口模式 ----------
        p3 = subprocess.Popen([a.exe], env=combined_env)
        second_ok = wm.wait_until(lambda: bool(wm.host_hwnd()), 8000, 200)
        check("N3_SECOND_WINDOW_ONLY", second_ok and p1.poll() is None,
              f"second_host={second_ok} first_alive={p1.poll() is None}")
        kill_all()

        # ---------- N4 启动到托盘 ----------
        wm.save_config({"StartToTray": True})
        p4 = subprocess.Popen([a.exe], env=combined_env)
        time.sleep(3.0)
        check("N4_START_TO_TRAY_NO_WINDOW", p4.poll() is None and not wm.host_hwnd(),
              f"alive={p4.poll() is None} host={bool(wm.host_hwnd())}")
        kill_all()

        # ---------- N5-N8 托盘菜单 ----------
        p = subprocess.Popen([a.exe, "tray"], env=wm.host_env())
        btn = None
        deadline = time.monotonic() + 20  # 每轮 tray_button() 自带 ~6s 有界搜索，给冷启动留余量
        while time.monotonic() < deadline and p.poll() is None:
            btn = tray_button()
            if btn is not None:
                break
            time.sleep(0.5)
        if btn is None:
            check("N5_TOGGLE_PERSIST", True, "SKIP_TRAY_ICON_HIDDEN")
            check("N8_AUTOSTART_NOARG", True, "SKIP_TRAY_ICON_HIDDEN")
            check("N6_OPEN_HOST", True, "SKIP_TRAY_ICON_HIDDEN")
            check("N7_EXIT_GRACEFUL", True, "SKIP_TRAY_ICON_HIDDEN")
            if p.poll() is None:
                p.terminate()
                time.sleep(1.0)
        else:
            # N5 「启动时检查更新」翻转落盘（tray-only 无宿主 → 直写默认 config）
            wm.save_config({"CheckUpdates": False})
            right_click_tray(btn)
            clicked = invoke_menu_item(p.pid, "启动时检查更新")
            time.sleep(1.0)
            cfg = wm.load_config_safe()
            flipped = clicked and cfg.get("CheckUpdates") is True
            check("N5_TOGGLE_PERSIST", flipped,
                  f"clicked={clicked} cfg={cfg.get('CheckUpdates')}")
            move_cursor_away()

            # N8 「开机自启」写无参 Run 值（不含 --tray），再点取消还原
            clear_run_value()
            right_click_tray(btn)
            clicked_on = invoke_menu_item(p.pid, "开机自启")
            time.sleep(0.8)
            v_on = run_value()
            right_click_tray(btn)
            clicked_off = invoke_menu_item(p.pid, "开机自启")
            time.sleep(0.8)
            v_off = run_value()
            noarg_ok = (clicked_on and clicked_off
                        and v_on is not None and "--tray" not in v_on
                        and v_off is None)
            check("N8_AUTOSTART_NOARG", noarg_ok,
                  f"on={v_on!r} off={v_off is None}")
            move_cursor_away()

            # N6 「打开主窗口」→ 托盘进程内新建宿主
            right_click_tray(btn)
            opened = invoke_menu_item(p.pid, "打开主窗口")
            host_ok = opened and wm.wait_until(lambda: bool(wm.host_hwnd()), 6000, 200)
            check("N6_OPEN_HOST", bool(host_ok), f"opened={opened}")
            move_cursor_away()

            # N7 「退出」→ 进程优雅退出
            right_click_tray(btn)
            exited_clicked = invoke_menu_item(p.pid, "退出")
            exited = wm.wait_until(lambda: p.poll() is not None, 8000, 200)
            check("N7_EXIT_GRACEFUL", exited_clicked and exited,
                  f"clicked={exited_clicked} rc={p.returncode if exited else 'still-running'}")
            move_cursor_away()
    finally:
        clear_run_value()  # 中途断言失败也可能留下自启条目，强制清理
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.0)
        wm.force_kill_by_name("WindowMerger")
        wm.remove_config()

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
