# -*- coding: utf-8 -*-
"""自动更新 e2e 回归：本地 HTTP 服务模拟 GitHub releases/latest + zip asset，
宿主经 WM_UPDATE_API 指过去（src/Updater.cs 的测试钩子）。弹窗确认流全走一遍：
  检查（4s 自动检查可能抢跑，与手动点击幂等）→ 断言 Available（发现即自动弹确认框）
  → 点确认框"立即更新" → 下载 → 自动重启安装
  → 断言旧 PID 退出 / 新 PID 从原 exe 路径运行 / 服务端收到 zip 请求 / .old 残留最终清掉
更新按钮按 AutomationId=UpdateButton 定位，UIA Name 随状态机变化 = 状态探针；确认框 =
进程内除宿主主窗外带 UpdateConfirm 按钮的顶层窗口（all_windows_of_pid 含 owned 弹层）。
InvokePattern 进程内直调，锁屏会话可用，不依赖遮挡/前台。
用法: uv run tools\\tests\\update_e2e_test.py [--exe 路径]
"""
import argparse
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

UPDATE_VERSION = "9.9.9"  # 远大于任何真实版本，IsNewer 必真


def build_zip(exe: str, tmpdir: Path) -> Path:
    """模拟 CI stage 产物：固定 entry 名 WindowMerger.exe（tools/ci/release.py 约定）。"""
    zip_path = tmpdir / f"WindowMerger-{UPDATE_VERSION}-win-x64.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, "WindowMerger.exe")
    return zip_path


def start_server(zip_path: Path):
    """127.0.0.1 随机端口：GET /releases/latest → 假 JSON（asset 指向本机 zip）。"""
    class Handler(http.server.BaseHTTPRequestHandler):
        api_hits = 0
        zip_hits = 0

        def do_GET(self):
            if self.path.startswith("/releases/latest"):
                Handler.api_hits += 1
                print("UPDATE_API_HIT", flush=True)
                body = json.dumps({
                    "tag_name": f"v{UPDATE_VERSION}",
                    "assets": [{
                        "name": zip_path.name,
                        "browser_download_url": f"http://127.0.0.1:{srv.port}/{zip_path.name}",
                    }],
                }).encode()
                self._send(200, body, "application/json")
            elif self.path.startswith(f"/{zip_path.name}"):
                Handler.zip_hits += 1
                print("UPDATE_ZIP_HIT", flush=True)
                self._send(200, zip_path.read_bytes(), "application/zip")
            else:
                self._send(404, b"{}", "application/json")

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # 静默默认访问日志
            pass

    class _Srv(http.server.ThreadingHTTPServer):
        daemon_threads = True

    srv = _Srv(("127.0.0.1", 0), Handler)
    srv.port = srv.server_address[1]  # Handler 的下载地址与 run_flow 的 API 地址共用
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


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


def confirm_update_dialog(host_hwnd: int, timeout_s: float = 6) -> bool:
    """等确认框出现并点"立即更新"（发现即自动弹出，正常 <1s）。注意 wm.wait_until 只回
    布尔，要拿句柄必须自己轮询；owned 弹窗在宿主 UIA 子树里也能走到（实测），按窗口找更稳。"""
    dlg = None
    deadline = time.monotonic() + timeout_s
    while dlg is None and time.monotonic() < deadline:
        dlg = find_update_dialog(host_hwnd)
        if dlg is None:
            time.sleep(0.2)
    if dlg is None:
        print("FAIL_NO_DIALOG")
        dump_dialog_failure(host_hwnd)
        return False
    for _ in range(5):  # UIA 偶发瞬态 COM 错误（句柄与取元素之间窗口变动），重试
        try:
            btn = wm_uia.find_by_automation_id(wm_uia.element_from_handle(dlg), "UpdateConfirm")
            if btn is not None:
                wm_uia.invoke(btn)
                return True
        except Exception:
            time.sleep(0.2)
    print("FAIL_NO_CONFIRM_BUTTON")
    dump_dialog_failure(host_hwnd)
    return False


def cancel_update_dialog(host_hwnd: int) -> None:
    """兜底清理：确认框若还开着（新实例自动检查会再弹），先取消再关宿主。"""
    dlg = find_update_dialog(host_hwnd)
    if not dlg:
        return
    try:
        el = wm_uia.element_from_handle(dlg)
        btn = wm_uia.find_by_automation_id(el, "UpdateCancel")
        if btn is not None:
            wm_uia.invoke(btn)
            time.sleep(0.3)
    except Exception:
        pass


def wait_phase(hwnd: int, needle: str, timeout_s: float) -> bool:
    def hit():
        return needle in (update_button_name(hwnd) or "")
    return wm.wait_until(hit, timeout_s * 1000, 300)


def run_flow(exe: str, srv) -> bool:
    env = {**os.environ, "WM_UPDATE_API": f"http://127.0.0.1:{srv.port}/releases/latest"}
    host = subprocess.Popen([exe], env=env)
    old_pid = host.pid
    time.sleep(3.5)
    hwnds = wm.host_hwnds()
    if not hwnds:
        print("FAIL_NO_HOST")
        return False
    # 测试宿主缩小 + 停左屏（AGENTS：不占用户主屏；钉位后 UIA 照常工作）
    hx, hy = wm.park_on_left_or_primary(900, 600)
    for h in hwnds:
        wm.set_window_pos(h, None, hx, hy, 900, 600, wm.SWP_NOZORDER)
    hwnd = hwnds[0]
    exe_file = Path(exe)
    old_file = Path(str(exe_file) + ".old")
    upd_file = Path(str(exe_file) + ".update")

    # ① 检查：自动检查（config.CheckUpdates=true 时 4s 后触发）可能已抢跑成 Available
    #（发现即自动弹确认框，宿主按钮此后不再点——模态期间点不到）
    name = update_button_name(hwnd) or ""
    if "发现新版本" not in name:
        if not click_update(hwnd):
            return False
        if not wait_phase(hwnd, "发现新版本", 10):
            print(f"FAIL_NO_AVAILABLE name={update_button_name(hwnd)!r}")
            return False
    if srv.RequestHandlerClass.api_hits < 1:
        print("FAIL_NO_API_REQUEST")
        return False
    print("CHECK_OK")

    # ② 确认框点"立即更新" → 下载 → 自动重启安装：旧进程退出、新进程从原 exe 路径跑起来
    # （偶发丢弹窗兜底：Available 态再点一次按钮本就重新弹确认框；仍失败则 DIAG 现场已打）
    if not confirm_update_dialog(hwnd):
        if not click_update(hwnd):
            return False
        if not confirm_update_dialog(hwnd):
            return False
    print("CONFIRM_OK")

    def restarted():
        pids = [p for p in wm.pids_by_name("WindowMerger") if wm.main_windows_of_pid(p)]
        return bool(pids) and old_pid not in pids

    if not wm.wait_until(restarted, 20000, 300):
        print("FAIL_NO_RESTART")
        return False
    if srv.RequestHandlerClass.zip_hits < 1:
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

    # 新实例 UI 完整可用（更新按钮存在且回到可点状态：Idle 或再次 Available）
    final = update_button_name(wm.host_hwnds()[0]) or ""
    if final not in ("", None) and ("检查更新" in final or "发现新版本" in final):
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
    with tempfile.TemporaryDirectory() as tmp:
        srv = start_server(build_zip(a.exe, Path(tmp)))
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
