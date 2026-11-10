# -*- coding: utf-8 -*-
"""自动更新 e2e 回归：本地 HTTP 服务模拟 GitHub releases/latest + zip asset，
宿主经 WM_UPDATE_API 指过去（src/Updater.cs 的测试钩子）。全流程走一遍：
  Idle 断言顶条更新按钮隐藏（无更新不显示图标；须赶在启动 4s 自动检查完成前断言）
  → 自动检查发现新版本：顶条功能区最左现身「发现新版本 ⬇」并自动弹确认框
  → 取消确认框（留在 Available，顶条保持）
  → 点 ⬇ 直接下载安装（不再弹框、不再检查——若误弹框会停在确认等待，restarted
    超时即隐性断言）→ 自动重启
  → 断言旧 PID 退出 / 新 PID 从原 exe 路径运行 / 服务端收到 zip 请求 / .old 残留最终清掉
被测宿主环境剥掉 WM_UPDATE_OFF（wm.py 导入即注入 + run_all 全局注入）——启动自动检查
是唯一检查入口，剥掉才有检查发生。
更新按钮按 AutomationId=UpdateButton 定位，UIA Name 随状态机变化 = 状态探针（按钮只在
Available/Downloading 可见，Idle 隐藏）；确认框 = 进程内除宿主主窗外带 UpdateConfirm
按钮的顶层窗口（all_windows_of_pid 含 owned 弹层）。
InvokePattern 进程内直调，锁屏会话可用，不依赖遮挡/前台。
用法: uv run tools\\tests\\update_e2e_test.py [--exe 路径]
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia
from fake_gh_api import FakeGitHubApi, zip_bytes

UPDATE_VERSION = "9.9.9"  # 远大于任何真实版本，IsNewer 必真


def start_server(exe: str) -> FakeGitHubApi:
    """127.0.0.1 随机端口：GET /releases/latest → 假 JSON（asset 指向本机 zip，
    内存打包固定 entry 名 WindowMerger.exe——tools/ci/release.py stage 约定）。"""
    api = FakeGitHubApi()
    api.configure(tag=f"v{UPDATE_VERSION}",
                  assets=[(f"WindowMerger-{UPDATE_VERSION}-win-x64.zip",
                           zip_bytes({"WindowMerger.exe": Path(exe).read_bytes()}))])
    api.start()
    return api


def update_button_name(hwnd: int) -> str | None:
    """更新按钮当前 UIA Name（=状态文案）；按钮/窗口不存在返回 None。"""
    try:
        el = wm_uia.element_from_handle(hwnd)
        btn = wm_uia.find_by_automation_id(el, "UpdateButton")
    except Exception:
        return None
    return None if btn is None else wm_uia.name_of(btn)


def click_update(hwnd: int) -> bool:
    el = wm_uia.element_from_handle(hwnd)
    btn = wm_uia.find_by_automation_id(el, "UpdateButton")
    if btn is None:
        print("FAIL_NO_UPDATE_BUTTON")
        return False
    wm_uia.invoke(btn)
    return True


def update_button_hidden(hwnd: int) -> bool:
    """Idle 态更新按钮必须不可见：UIA 树里不存在（WPF 对 Collapsed 子树的处理两种表现
    均算隐藏），或存在但 IsOffscreen=True。查不出（COM 瞬态错误）按可见算，让断言暴露。"""
    try:
        el = wm_uia.element_from_handle(hwnd)
        btn = wm_uia.find_by_automation_id(el, "UpdateButton")
    except Exception:
        return False
    if btn is None:
        return True
    try:
        return bool(btn.IsOffscreen)
    except Exception:
        return False


def find_update_dialog(host_hwnd: int) -> int | None:
    """确认对话框 = 进程里除宿主主窗外、带 UpdateConfirm 按钮的可见顶层窗口。"""
    for h in wm.all_windows_of_pid(wm.pid_of(host_hwnd)):
        if h == host_hwnd:
            continue
        try:
            el = wm_uia.element_from_handle(h)
            btn = wm_uia.find_by_automation_id(el, "UpdateConfirm")
        except Exception:
            continue
        if btn is not None:
            return h
    return None


def dump_dialog_failure(host_hwnd: int) -> None:
    """FAIL_NO_DIALOG 现场：进程存活 + 顶层窗口清单 + UIA 文本（状态栏通知 3s TTL 内
    能读到 PromptUpdateAsync 的报因文案）。"""
    try:
        print(f"DIAG alive={bool(wm.pids_by_name('WindowMerger'))}", flush=True)
        for h in wm.all_windows_of_pid(wm.pid_of(host_hwnd)):
            print(f"DIAG WIN h={h:#x} cls={wm.get_class_name(h)[:40]} "
                  f"vis={wm.is_window_visible(h)} title={wm.get_text(h)!r}", flush=True)
        import uiautomation as auto
        el = wm_uia.element_from_handle(host_hwnd)
        for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=8):
            if c.ControlTypeName == "TextControl" and (c.Name or "").strip():
                print(f"DIAG TEXT {c.Name!r}", flush=True)
    except Exception as ex:
        print(f"DIAG_ERR {type(ex).__name__}: {ex}", flush=True)


def wait_update_dialog(host_hwnd: int, timeout_s: float) -> int | None:
    """等确认框出现返回句柄（发现即自动弹出，正常 4~5s）。wm.wait_until 只回布尔，
    要拿句柄必须自己轮询；owned 弹窗在宿主 UIA 子树里也能走到（实测），按窗口找更稳。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        dlg = find_update_dialog(host_hwnd)
        if dlg is not None:
            return dlg
        time.sleep(0.2)
    return None


def cancel_dialog_hwnd(dlg: int) -> bool:
    """点确认框的取消按钮（UIA 偶发瞬态 COM 错误——句柄与取元素之间窗口变动，重试）。"""
    for _ in range(5):
        try:
            btn = wm_uia.find_by_automation_id(wm_uia.element_from_handle(dlg), "UpdateCancel")
            if btn is not None:
                wm_uia.invoke(btn)
                return True
        except Exception:
            time.sleep(0.2)
    return False


def cancel_update_dialog(host_hwnd: int) -> None:
    """兜底清理：确认框若还开着（新实例自动检查会再弹），先取消再关宿主。"""
    dlg = find_update_dialog(host_hwnd)
    if not dlg:
        return
    try:
        cancel_dialog_hwnd(dlg)
        time.sleep(0.3)
    except Exception:
        pass


def wait_phase(hwnd: int, needle: str, timeout_s: float) -> bool:
    def hit():
        return needle in (update_button_name(hwnd) or "")
    return wm.wait_until(hit, timeout_s * 1000, 300)


def run_flow(exe: str, srv) -> bool:
    # 剥掉 WM_UPDATE_OFF（run_all 全局注入）：本测试必须让启动自动检查活着——它是唯一
    # 检查入口；WM_UPDATE_API 指本地假服务，不会碰真实 GitHub API
    env = {k: v for k, v in os.environ.items() if k != "WM_UPDATE_OFF"}
    env["WM_UPDATE_API"] = f"http://127.0.0.1:{srv.port}/releases/latest"
    host = subprocess.Popen([exe], env=env)
    old_pid = host.pid
    # 窗口一出现立刻断言 Idle 隐藏：启动 4s 定时器一触发、假 API 一应答按钮就会现身，
    # 拖到 park 之后断言会和自动检查赛跑（3.5s sleep + park 已贴着 4s 红线）
    if not wm.wait_until(lambda: wm.host_hwnds(), 8000, 200):
        print("FAIL_NO_HOST")
        return False
    hwnds = wm.host_hwnds()
    hwnd = hwnds[0]
    time.sleep(0.5)  # 让 WPF 视觉树/UIA 子树就绪（窗口出现 + 0.5s 仍在 4s 定时器红线前）
    if not update_button_hidden(hwnd):
        print("FAIL_IDLE_VISIBLE")
        return False
    print("IDLE_HIDDEN_OK")
    # 测试宿主缩小 + 停左屏（AGENTS：不占用户主屏；钉位后 UIA 照常工作）
    hx, hy = wm.park_on_left_or_primary(900, 600)
    for h in hwnds:
        wm.set_window_pos(h, None, hx, hy, 900, 600, wm.SWP_NOZORDER)
    exe_file = Path(exe)
    old_file = Path(str(exe_file) + ".old")
    upd_file = Path(str(exe_file) + ".update")

    # ② 自动检查发现新版本：顶条功能区最左现身「发现新版本 ⬇」并自动弹确认框
    dlg = wait_update_dialog(hwnd, 15)
    if dlg is None:
        print(f"FAIL_NO_AUTO_DIALOG name={update_button_name(hwnd)!r}")
        dump_dialog_failure(hwnd)
        return False
    if srv.api_hits < 1:
        print("FAIL_NO_API_REQUEST")
        return False
    print("CHECK_OK")

    # ③ 取消确认框 → 留在 Available（顶条更新组保持；点 ⬇ = 直接下载）
    if not cancel_dialog_hwnd(dlg):
        print("FAIL_NO_CANCEL_BUTTON")
        dump_dialog_failure(hwnd)
        return False
    if not wait_phase(hwnd, "发现新版本", 5):
        print(f"FAIL_NOT_AVAILABLE_AFTER_CANCEL name={update_button_name(hwnd)!r}")
        return False
    print("CANCEL_OK")

    # ④ 点 ⬇ 直接下载安装（不再弹框、不再检查）→ 自动重启：旧进程退出、新进程从原
    # exe 路径跑起来
    if not click_update(hwnd):
        return False
    print("DOWNLOAD_CLICKED")

    def restarted():
        pids = [p for p in wm.pids_by_name("WindowMerger") if wm.main_windows_of_pid(p)]
        return bool(pids) and old_pid not in pids

    if not wm.wait_until(restarted, 20000, 300):
        print("FAIL_NO_RESTART")
        return False
    if srv.zip_hits < 1:
        print("FAIL_NO_ZIP_REQUEST")
        return False
    print("DOWNLOAD_OK")
    new_pids = [p for p in wm.pids_by_name("WindowMerger") if wm.main_windows_of_pid(p)]
    new_path = wm.image_path_of_pid(new_pids[0]) if new_pids else None
    if not new_path or os.path.normcase(new_path) != os.path.normcase(exe):
        print(f"FAIL_PATH_MISMATCH new={new_path}")
        return False
    print(f"RESTART_OK old={old_pid} new={new_pids[0]}")

    # 新实例的重试清理最终删掉 .old/.update（旧进程释放锁后）
    def leftovers_gone():
        return not old_file.exists() and not upd_file.exists()

    if not wm.wait_until(leftovers_gone, 15000, 500):
        print(f"FAIL_LEFTOVERS old={old_file.exists()} update={upd_file.exists()}")
        return False
    print("CLEANUP_OK")

    # 新实例 UI 完整可用。被剥过的环境随宿主继承 → 新实例 4s 后也会自动检查并弹框，
    # 而这里通常在其检查完成前读取：隐藏（不在 UIA 树）或 Idle/Available 文案都算健康，
    # 垃圾值才算炸；随后 main 的兜底清理会取消可能弹出的确认框
    try:
        new_el = wm_uia.element_from_handle(wm.host_hwnds()[0])
        new_btn = wm_uia.find_by_automation_id(new_el, "UpdateButton")
    except Exception as ex:
        print(f"FAIL_FINAL_UIA {type(ex).__name__}: {ex}")
        return False
    if new_btn is None:
        print("FINAL_PHASE HIDDEN_IDLE")
    else:
        final = wm_uia.name_of(new_btn) or ""
        if "检查更新" in final or "发现新版本" in final:
            print(f"FINAL_PHASE {final}")
        else:
            print(f"FAIL_FINAL_PHASE {final!r}")
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 运行中的宿主优雅关（保存配置 + 释放子窗口）
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.3)
    if not Path(a.exe).exists():
        print("FAIL_NO_EXE")
        return 1

    ok = False
    srv = start_server(a.exe)
    try:
        ok = run_flow(a.exe, srv)
    finally:
        # 新实例自动检查会再弹确认框，先取消再优雅关（模态框开着 WM_CLOSE 语义不明）
        for h in wm.host_hwnds():
            cancel_update_dialog(h)
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.2)
        srv.shutdown()
        # 优雅关兜底失败再树杀，不给套件留进程
        for p in wm.pids_by_name("WindowMerger"):
            wm.force_kill_pid(p)

    print("RESULT PASS" if ok else "RESULT FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
