# -*- coding: utf-8 -*-
"""CLI 参数解析边界回归（System.CommandLine 命令式 CLI：src/Cli.cs + HostWindow.Attach.cs 报因路径）：
  C1 merge 位置参数 `exe merge notepad mspaint` 命中双侧吸附
  C2 旗标缺参 `exe merge --left` → MessageBox 报因 + 退出码 1，无主窗
  C3 未知旗标 `exe merge --unknown xxx` → MessageBox + 退出码 1；
     根命令旧旗标 `exe --tray` 同样报因（完全命令式，无兼容别名）
  C4 进程名大小写不敏感 + .exe 后缀剥离（NOTEPAD.EXE ≡ notepad）
  C5 名字匹配不到 → "未找到 X 的窗口，已跳过"；双目标后条覆盖前条（ShowNotice 单槽）
  C6 --left-exe 路径不存在 → "路径不存在：X，已跳过"
  C7 tray 冒烟：常驻无主窗（单实例 mutex/生命周期细节见 snap_capture_test S6）
  C8 detect 冒烟：stdout 一行 JSON、退出码 0（检测细节见 snap_capture_test S1/S4）
  C9 --help → 用法 MessageBox + 退出码 0（GUI 无控制台，lib 帮助输出不可见，改弹框）
  C10 多余位置参数 `exe merge a b c` → MessageBox + 退出码 1
通知 3 秒 TTL：宿主窗口出现后 ~1.5s 内读状态栏（attach/notice 在 Loaded 即发生）。
用法: uv run tools\\tests\\cli_args_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import json
import subprocess
import sys
import tempfile
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
    """回归保护：弹框用例若意外常驻（解析语义回归成"静默落位置参数"），清理掉再继续，
    防止残留宿主污染后续用例的 host_hwnd 探测。"""
    if p.poll() is None:
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.0)
        wm.force_kill_by_name("WindowMerger")
        time.sleep(0.5)


def start_and_status(exe: str, *args: str, pin: tuple | None = None,
                     wait: float = 3.0) -> tuple[int, str | None]:
    """启动宿主（带任意参数）→ 读状态栏。注意通知 3s 过期，读晚了只能拿到常态文案。"""
    subprocess.Popen([exe, *args], env=wm.host_env())
    time.sleep(wait)
    hm = wm.host_hwnd()
    if not hm:
        return 0, None
    if pin:
        wm.set_window_pos(hm, None, *pin, wm.SWP_NOZORDER)
        time.sleep(1.5)
    st = wm_uia.status_text(hm)
    return hm, st


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
    pin = wm.test_layout()["host"]

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    kill_all()
    t1 = Path(tempfile.gettempdir(), "wmcli1.txt")
    t1.write_text("cli-args", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    subprocess.Popen(["mspaint"])
    if not wm.wait_main_windows("Notepad", "mspaint"):
        print("FAIL_TARGETS_NOT_RUNNING")
        return 1

    # ---------- C1 merge 位置参数 ----------
    hm, _ = start_and_status(a.exe, "merge", "notepad", "mspaint", pin=pin)
    if not hm:
        check("C1_HOST", False)
    else:
        wm.set_topmost(hm, True)
        time.sleep(0.4)
        hr = wm.get_window_rect(hm)
        avail = hr.Right - hr.Left - 12
        mid_y = (hr.Top + hr.Bottom) // 2
        l = wm.proc_name_of(wm.window_from_point(hr.Left + 2 + int(avail * 0.25), mid_y)).lower()
        r = wm.proc_name_of(wm.window_from_point(hr.Left + 2 + int(avail * 0.75), mid_y)).lower()
        check("C1_POSITIONAL_ATTACH", l == "notepad" and r == "mspaint", f"L={l} R={r}")
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.5)
    wm.force_kill_by_name("Notepad", "mspaint")
    time.sleep(0.8)

    # ---------- C2 旗标缺参 ----------
    p, shown = start_dialog_case(a.exe, "merge", "--left")
    check("C2_MISSING_VALUE_RC1", shown and p.returncode == 1 and not wm.host_hwnd(),
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    # ---------- C3 未知旗标 + 根命令旧旗标（无兼容别名） ----------
    p, shown = start_dialog_case(a.exe, "merge", "--unknown", "xxx")
    check("C3_UNKNOWN_FLAG_RC1", shown and p.returncode == 1,
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)
    p, shown = start_dialog_case(a.exe, "--tray")
    check("C3B_LEGACY_FLAG_RC1", shown and p.returncode == 1,
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    # ---------- C4 大小写 + .exe 后缀（命名形式） ----------
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    hm, _ = start_and_status(a.exe, "merge", "--left", "NOTEPAD.EXE", pin=pin)
    if not hm:
        check("C4_HOST", False)
    else:
        wm.set_topmost(hm, True)
        time.sleep(0.4)
        hr = wm.get_window_rect(hm)
        probe_y = (hr.Top + hr.Bottom) // 2
        h1 = wm.window_from_point(hr.Left + 2 + int((hr.Right - hr.Left - 12) * 0.25), probe_y)
        check("C4_CASE_EXE_ATTACH", wm.proc_name_of(h1).lower() == "notepad",
              f"LEFT_HIT={wm.proc_name_of(h1)}")
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.5)
    wm.force_kill_by_name("Notepad")
    time.sleep(0.8)

    # ---------- C5 名字匹配不到（无 notepad/mspaint 环境）----------
    hm, st = start_and_status(a.exe, "merge", "--left", "zznope12345")
    check("C5_ALIVE", bool(hm))
    check("C5_NOT_FOUND_NOTICE", bool(st and "未找到 zznope12345 的窗口" in st), f"status={st!r}")
    if hm:
        wm.post_close(hm)
        time.sleep(1.5)

    # ---------- C5b 双目标报因后条覆盖前条（ShowNotice 单槽语义仍成立） ----------
    hm, st = start_and_status(a.exe, "merge", "zznope12345", "zznope98765")
    check("C5B_ALIVE", bool(hm))
    check("C5B_LAST_NOTICE_WINS",
          bool(st and "未找到 zznope98765 的窗口" in st and "zznope12345" not in st),
          f"status={st!r}")
    if hm:
        wm.post_close(hm)
        time.sleep(1.5)

    # ---------- C6 --left-exe 路径不存在 ----------
    hm, st = start_and_status(a.exe, "merge", "--left", "zznope12345",
                              "--left-exe", "D:\\no\\such\\dir\\zznope.exe")
    check("C6_ALIVE", bool(hm))
    check("C6_PATH_MISSING_NOTICE", bool(st and "路径不存在" in st and "已跳过" in st),
          f"status={st!r}")
    if hm:
        wm.post_close(hm)
        time.sleep(1.5)

    # ---------- C7 tray 冒烟 ----------
    p = subprocess.Popen([a.exe, "tray"], env=wm.host_env())
    time.sleep(2.5)
    check("C7_TRAY_RESIDENT", p.poll() is None and not wm.host_hwnd(),
          f"poll={p.poll()}")
    if p.poll() is None:
        p.terminate()
        time.sleep(1.0)

    # ---------- C8 detect 冒烟 ----------
    p = subprocess.run([a.exe, "detect"], capture_output=True, timeout=30)
    try:
        d = json.loads(p.stdout.decode("utf-8", errors="replace"))
    except Exception:
        d = {}
    check("C8_DETECT_JSON", p.returncode == 0 and "ok" in d,
          f"rc={p.returncode} out={p.stdout[:80]!r}")

    # ---------- C9 --help 用法弹框，退出码 0 ----------
    p, shown = start_dialog_case(a.exe, "--help")
    check("C9_HELP_RC0", shown and p.returncode == 0 and not wm.host_hwnd(),
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    # ---------- C10 多余位置参数 ----------
    p, shown = start_dialog_case(a.exe, "merge", "a1", "b2", "zzextra")
    check("C10_EXTRA_ARG_RC1", shown and p.returncode == 1 and not wm.host_hwnd(),
          f"rc={p.returncode} dialog={shown}")
    ensure_closed(p)

    wm.remove_config()
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
