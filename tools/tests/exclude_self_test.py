# -*- coding: utf-8 -*-
"""排除自身回归：B/C 两个 WM_NO_TRAY 实例并存（不起托盘、不占 mutex），C 打开选择器时
候选必须排除另一个自己的窗口（B 的宿主不进候选——WindowLocator.IsOtherSelf）。
原"实例 C 用 merge --left <B 的 PID> 抓 B"路径已随 merge 子命令退役（单进程多宿主+
无参单实例唤起后，占 mutex 的第二实例根本无法存在）；候选排除是同一判据的现存面。
用法: uv run tools/\tests\\exclude_self_test.py [--exe 路径]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia
import uiautomation as auto


def _spawn_host(exe: str) -> int:
    """起一扇 WM_NO_TRAY 宿主（无托盘、关窗即退出），返回 hwnd；30×0.3s 轮询兜 CI 冷启动。"""
    subprocess.Popen([exe], env=wm.host_env())
    for _ in range(30):
        pids = [p for p in wm.pids_by_name("WindowMerger") if wm.main_windows_of_pid(p)]
        if pids:
            return wm.main_windows_of_pid(pids[0])[0]
        time.sleep(0.3)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 清理（优雅关；实例可能持有用户窗口，不强杀）
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.3)

    # 受害者 B：普通实例（等主窗真实出现，CI 冷启动 WPF 首启竞速兜底）
    hb = _spawn_host(a.exe)
    if not hb:
        print("FAIL_NO_B")
        return 1
    rb = wm.get_window_rect(hb)

    # 抓取者 C：第二个并存实例，打开自己的选择器
    hc = _spawn_host(a.exe)
    if not hc:
        print("FAIL_NO_C")
        return 1

    hint = wm_uia.find_by_automation_id(wm_uia.element_from_handle(hc), "_paneHint0")
    if hint is None:
        print("FAIL_NO_HINT")
        return 1
    wm_uia.invoke(hint)
    picker = wm_uia._wait_picker(hc)
    if picker is None:
        print("FAIL_NO_PICKER")
        return 1
    rows = [c.Name or "" for c, _ in auto.WalkControl(picker, includeTop=False, maxDepth=8)
            if c.ControlTypeName in ("ListItemControl", "DataItemControl")]
    wm_uia._invoke_named(picker, "取消")

    b_title = wm.get_text(hb)
    # 精确匹配 B 宿主标题（子串 "windowmerger" 会误伤标题里恰含项目名的窗口——
    # VS Code 打开本仓库时标题就带 "WindowMerger"，实测假阳性）
    grabbed_like = b_title in rows
    rb2 = wm.get_window_rect(hb)
    moved = rb2.Left != rb.Left or rb2.Top != rb.Top

    ok = bool(rows) and not grabbed_like and not moved
    print(f"rows={rows}")
    print(f"B title={b_title!r} tool={wm.is_attached(hb)} moved={moved}")
    print("EXCLUDE_SELF_TEST_DONE")
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
