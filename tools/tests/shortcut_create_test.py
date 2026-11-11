# -*- coding: utf-8 -*-
"""快捷方式生成回归：mspaint 单侧吸附（无 notepad）→ UIA Invoke _shortcutButton →
读桌面新 .lnk（WScript.Shell COM）断言 TargetPath/Arguments 含 --left/--left-exe
完整路径 → 删掉 .lnk。只杀自己拉起的 mspaint，绝不碰 notepad。
原 ShortcutCreateTest.ps1。
用法: uv run tools/\tests\\shortcut_create_test.py [--exe 路径]
mspaint 被占用时 SKIP 不强杀。
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    if wm.pids_by_name("mspaint"):
        print("SKIP_MSPAINT_RUNNING")
        return 0

    # 快捷方式文件名含中文前缀（窗口合并），WScript.Shell 内部走 ANSI 保存——
    # 系统 ANSI 代码页编码不了中文时（en-US CP1252）保存必败（CI 实测 Unable to
    # save shortcut "???? - mspaint.lnk"）。非 CJK 代码页 SKIP，等产品做 ASCII 回退名
    import ctypes
    acp = ctypes.windll.kernel32.GetACP()
    if acp != 936:
        print(f"SKIP_NON_CJK_ANSI_CODEPAGE acp={acp}")
        return 0

    # 桌面可写探测（区分权限问题与编码问题）
    desktop_probe = Path(wm.desktop_dir()) / "wm_probe.txt"
    try:
        desktop_probe.write_text("probe", encoding="ascii")
        desktop_probe.unlink()
        print("DIAG desktop writable: True")
    except Exception as e:
        print(f"DIAG desktop writable: False ({e})")

    # 清理（mspaint 侧；其他运行中宿主优雅关）
    wm.graceful_close_by_name("WindowMerger")
    wm.force_kill_by_name("mspaint")
    time.sleep(1.3)

    # 目标窗口：小尺寸停到左侧 100% 屏（绝不占用户 4K）
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    mp_pids = [p for p in wm.pids_by_name("mspaint") if wm.main_windows_of_pid(p)]
    if mp_pids:
        px, py = wm.park_on_left_or_primary(900, 650)  # 单屏（CI）停主屏左上，不出屏
        wm.set_window_pos(wm.main_windows_of_pid(mp_pids[0])[0], None,
                          px, py, 900, 650, wm.SWP_NOZORDER)

    subprocess.Popen([a.exe, "--left", "mspaint"])
    time.sleep(4)

    hosts = wm.host_hwnds()
    if not hosts:
        print("FAIL_NO_HOST")
        wm.force_kill_by_name("mspaint")
        return 1
    hm = hosts[0]
    # 测试宿主缩小 + 停到左显示器（config 尺寸可能巨大，如存过跨双屏拼接）
    px, py = wm.park_on_left_or_primary(900, 600)
    wm.set_window_pos(hm, None, px, py, 900, 600, wm.SWP_NOZORDER)

    # UIA Invoke 快捷方式按钮（x:Name → AutomationId）
    root_el = wm_uia.element_from_handle(hm)
    btn = wm_uia.find_by_automation_id(root_el, "_shortcutButton")
    if btn is None:
        print("FAIL_NO_BUTTON")
        wm.graceful_close_by_name("WindowMerger")
        wm.force_kill_by_name("mspaint")
        return 1
    wm_uia.invoke(btn)
    time.sleep(2)

    # 诊断：读状态栏文本（应用把成功/失败原因写在那里）+ WScript.Shell COM 可用性
    try:
        import uiautomation as auto
        for c, _ in auto.WalkControl(wm_uia.element_from_handle(hm),
                                     includeTop=False, maxDepth=6):
            if c.ControlTypeName == "TextControl" and c.Name and len(c.Name) > 6:
                print(f"DIAG status: {c.Name!r}")
    except Exception as e:
        print(f"DIAG status read failed: {e}")
    try:
        import comtypes.client
        shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
        print("DIAG WScript.Shell COM OK")
    except Exception as e:
        print(f"DIAG WScript.Shell COM FAILED: {e}")

    # 定位新 .lnk：文件名前缀 = 中文应用名（从码点构造）
    prefix = "".join(chr(c) for c in (0x7A97, 0x53E3, 0x5408, 0x5E76))
    desktop = wm.desktop_dir()
    candidates = []
    now = time.time()
    for f in Path(desktop).glob("*.lnk"):
        if f.name.startswith(prefix) and now - f.stat().st_mtime < 120:
            candidates.append(f)
    if not candidates:
        # 诊断：吸附是否成立（应用只在有吸附时写 .lnk）+ 桌面现有 lnk
        mp = wm.main_windows_by_name("mspaint")
        print(f"DIAG attached={bool(mp) and wm.is_attached(mp[0][1])} desktop={desktop}")
        print(f"DIAG desktop_lnk={[f.name for f in Path(desktop).glob('*.lnk')][:10]}")
        print("FAIL_NO_LNK")
        wm.graceful_close_by_name("WindowMerger")
        wm.force_kill_by_name("mspaint")
        return 1
    lnk = max(candidates, key=lambda f: f.stat().st_mtime)

    s = wm_uia.shell_shortcut(str(lnk))
    print(f"TARGET={s.TargetPath}")
    print(f"ARGS={s.Arguments}")
    print(f"ICON={s.IconLocation}")
    ok_args = re.search(r'--left\s+"?mspaint"?', s.Arguments)
    ok_exe = re.search(r'--left-exe\s+"?[^"]*mspaint\.exe', s.Arguments)
    ok_target = re.search(r"WindowMerger.*\.exe$", s.TargetPath)
    ok = bool(ok_args and ok_exe and ok_target)
    print("PASS_SHORTCUT" if ok else "FAIL_CONTENT")

    lnk.unlink(missing_ok=True)

    # 清理
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.force_kill_by_name("mspaint")
    print("SHORTCUT_TEST_DONE")
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
