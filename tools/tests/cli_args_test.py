# -*- coding: utf-8 -*-
"""CLI 边界回归（merge/tray 子命令已退役：CLI = 无参组合模式 + detect 两入口）：
  C1 未知旗标 → MessageBox 报因 + 退出码 1
  C2 根命令旧旗标 `exe --tray` 同样报因（完全命令式，无兼容别名）
  C3 未知位置参数 `exe a1 b2` → 报因（根命令无位置参数）
  C4 --help → 用法 MessageBox + 退出码 0
  C5 detect 冒烟：stdout 一行 JSON、退出码 0
  C6 无参组合模式冒烟：宿主出现（WM_NO_TRAY=1 → 无托盘、关窗即退出）
吸附环境搭法见 wm_uia.attach_via_panes（选择器路径）；单实例唤起/托盘菜单见 noargs_tray_test。
用法: uv run tools\\tests\\cli_args_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

DIALOG_CLASS = "#32770"  # Windows 标准对话框类（MessageBox 的窗口类）


def _close_dialog(pid: int) -> bool:
    """关闭该进程已弹出的 MessageBox（WM_CLOSE），供解析失败/用法用例收场。"""
    for h in wm.all_windows_of_pid(pid):
        if wm.get_class_name(h) == DIALOG_CLASS:
            wm.post_close(h)
            return True
    return False


def start_dialog_case(exe: str, *args: str) -> tuple[subprocess.Popen, bool]:
    """启动 → 等报因/用法 MessageBox 出现并 WM_CLOSE 关掉 → 等进程退出。
    返回 (进程, 弹窗是否出现过)。解析失败弹框会阻塞 OnStartup，进程退出码在关框后才产生。"""
    p = subprocess.Popen([exe, *args], env=wm.host_env())
    shown = wm.wait_until(lambda: _close_dialog(p.pid), 6000, 120)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and p.poll() is None:
        time.sleep(0.1)
    return p, shown


def ensure_closed(p: subprocess.Popen) -> None:
    """回归保护：弹框用例若意外常驻（解析语义回归），清理掉再继续，防残留宿主污染后续用例。"""
    if p.poll() is None:
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.0)
        wm.force_kill_by_name("WindowMerger")
        time.sleep(0.5)


def kill_all() -> None:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.5)


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

    # ---------- C1 未知旗标 ----------
    p, shown = start_dialog_case(a.exe, "--unknown", "xxx")
    check("C1_UNKNOWN_FLAG_RC1", shown and p.returncode == 1,
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    # ---------- C2 根命令旧旗标（无兼容别名） ----------
    p, shown = start_dialog_case(a.exe, "--tray")
    check("C2_LEGACY_FLAG_RC1", shown and p.returncode == 1,
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    # ---------- C3 未知位置参数（根命令无位置参数） ----------
    p, shown = start_dialog_case(a.exe, "a1", "b2")
    check("C3_STRAY_POSITIONAL_RC1", shown and p.returncode == 1,
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    # ---------- C4 --help 用法弹框，退出码 0 ----------
    p, shown = start_dialog_case(a.exe, "--help")
    check("C4_HELP_RC0", shown and p.returncode == 0 and not wm.host_hwnd(),
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    # ---------- C5 detect 冒烟 ----------
    p = subprocess.run([a.exe, "detect"], capture_output=True, timeout=30)
    try:
        d = json.loads(p.stdout.decode("utf-8", errors="replace"))
    except Exception:
        d = {}
    check("C5_DETECT_JSON", p.returncode == 0 and "ok" in d,
          f"rc={p.returncode} out={p.stdout[:80]!r}")

    # ---------- C6 无参组合模式冒烟（WM_NO_TRAY=1 → 无托盘、关窗即退出） ----------
    subprocess.Popen([a.exe], env=wm.host_env())
    host_ok = wm.wait_until(lambda: bool(wm.host_hwnd()), 8000, 200)
    check("C6_COMBINED_HOST", bool(host_ok), f"host={bool(wm.host_hwnd())}")
    if host_ok:
        wm.post_close(wm.host_hwnd())
        exited = wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
        check("C6_CLOSE_EXITS", bool(exited), f"exited={bool(exited)}")
    kill_all()

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
