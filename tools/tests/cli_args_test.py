# -*- coding: utf-8 -*-
"""CLI 参数解析边界回归（App.xaml.cs ParseArgs + HostWindow.Attach.cs 报因路径）：
  C1 位置参数 `exe notepad mspaint` ≡ 命名参数（双侧吸附命中）
  C2 旗标缺参 `exe --left` → 字面量落进位置参数 → 状态栏"未找到 --left 的窗口"，不崩
  C3 未知旗标 `exe --unknown xxx` → 两条"未找到"报因，不崩
  C4 进程名大小写不敏感 + .exe 后缀剥离（NOTEPAD.EXE ≡ notepad）
  C5 名字匹配不到 → "未找到 X 的窗口，已跳过"
  C6 --left-exe 路径不存在 → "路径不存在：X，已跳过"
通知 3 秒 TTL：宿主窗口出现后 ~1.5s 内读状态栏（attach/notice 在 Loaded 即发生）。
用法: uv run tools\\tests\\cli_args_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint。
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


def start_and_status(exe: str, *args: str, pin: tuple | None = None,
                     wait: float = 3.0) -> tuple[int, str | None]:
    """启动宿主（带任意参数）→ 读状态栏。注意通知 3s 过期，读晚了只能拿到常态文案。"""
    subprocess.Popen([exe, *args])
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

    kill_all()
    t1 = Path(tempfile.gettempdir(), "wmcli1.txt")
    t1.write_text("cli-args", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    subprocess.Popen(["mspaint"])
    if not wm.wait_main_windows("Notepad", "mspaint"):
        print("FAIL_TARGETS_NOT_RUNNING")
        return 1

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    # ---------- C1 位置参数 = 命名参数 ----------
    hm, _ = start_and_status(a.exe, "notepad", "mspaint", pin=pin)
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
    hm, st = start_and_status(a.exe, "--left")
    check("C2_ALIVE", bool(hm))
    check("C2_MISSING_VALUE_NOTICE", bool(st and "未找到 --left 的窗口" in st), f"status={st!r}")
    if hm:
        wm.post_close(hm)
        time.sleep(1.5)

    # ---------- C3 未知旗标 ----------
    # 两个位置参数各报一次因，但状态栏单行、后一条覆盖前一条（ShowNotice 单槽）——
    # 断言固化"最后一条可见"语义
    hm, st = start_and_status(a.exe, "--unknown", "zznope123")
    check("C3_ALIVE", bool(hm))
    check("C3_LAST_NOTICE_WINS",
          bool(st and "未找到 zznope123 的窗口" in st and "--unknown" not in st),
          f"status={st!r}")
    if hm:
        wm.post_close(hm)
        time.sleep(1.5)

    # ---------- C4 大小写 + .exe 后缀 ----------
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    hm, _ = start_and_status(a.exe, "--left", "NOTEPAD.EXE", pin=pin)
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
    hm, st = start_and_status(a.exe, "--left", "zznope12345")
    check("C5_ALIVE", bool(hm))
    check("C5_NOT_FOUND_NOTICE", bool(st and "未找到 zznope12345 的窗口" in st), f"status={st!r}")
    if hm:
        wm.post_close(hm)
        time.sleep(1.5)

    # ---------- C6 --left-exe 路径不存在 ----------
    hm, st = start_and_status(a.exe, "--left", "zznope12345",
                              "--left-exe", "D:\\no\\such\\dir\\zznope.exe")
    check("C6_ALIVE", bool(hm))
    check("C6_PATH_MISSING_NOTICE", bool(st and "路径不存在" in st and "已跳过" in st),
          f"status={st!r}")
    if hm:
        wm.post_close(hm)
        time.sleep(1.5)

    wm.remove_config()
    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
