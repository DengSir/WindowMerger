# -*- coding: utf-8 -*-
"""拉起吸附回归（无 notepad）：确保 mspaint 未运行 → 宿主带 --left mspaint
--left-exe 完整路径 启动 → 断言宿主自己拉起 mspaint 且 15s 内吸附成功
（TOOLWINDOW 置位）。原 LaunchAttachTest.ps1。
用法: py tools\\tests\\launch_attach_test.py [--exe 路径]
"""
import argparse
import datetime
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 运行中的宿主优雅关；用户开着的 mspaint 不碰
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.3)
    if wm.pids_by_name("mspaint"):
        print("SKIP_MSPAINT_RUNNING")
        return 0

    # 趁 mspaint 短暂起来时现场解析真实 exe 路径（打包应用路径含版本目录、
    # 更新后会变，绝不硬编码），再关掉
    mp = subprocess.Popen(["mspaint"])
    time.sleep(1.8)
    mp_pids = [p for p in wm.pids_by_name("mspaint") if wm.main_windows_of_pid(p)]
    if not mp_pids:
        print("FAIL_NO_MSPAINT")
        return 1
    mp_pid = mp_pids[0]
    mph = wm.main_windows_of_pid(mp_pid)[0]
    wm.set_window_pos(mph, None, -2300, 200, 900, 650, wm.SWP_NOZORDER)
    mp_path = wm.image_path_of_pid(mp_pid)
    wm.force_kill_pid(mp_pid)
    time.sleep(1.2)
    if not mp_path:
        print("FAIL_NO_PATH")
        return 1
    print(f"TARGET_PATH={mp_path}")

    # 名字 + 完整路径：mspaint 已关，宿主必须自己拉起并吸附
    host_start = datetime.datetime.now()
    host = subprocess.Popen([a.exe, "--left", "mspaint", "--left-exe", mp_path])
    time.sleep(4)
    # 测试宿主缩小 + 停到左显示器（config 尺寸可能巨大）
    for h in wm.host_hwnds():
        wm.set_window_pos(h, None, -2460, 120, 1000, 700, wm.SWP_NOZORDER)

    # 轮询 15s：mspaint 重现 且 已吸附（TOOLWINDOW）
    ok = False
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        time.sleep(0.5)
        mp_pids = [p for p in wm.pids_by_name("mspaint") if wm.main_windows_of_pid(p)]
        if mp_pids:
            pid = mp_pids[0]
            launched_by_host = wm.proc_start_time(pid) > host_start
            attached = wm.is_toolwindow(wm.main_windows_of_pid(pid)[0])
            print(f"STATE launchedByHost={launched_by_host} attached={attached} "
                  f"path={wm.image_path_of_pid(pid)}")
            if launched_by_host and attached:
                ok = True
                break

    # 清理
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("mspaint")

    print("RESULT PASS" if ok else "RESULT FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
