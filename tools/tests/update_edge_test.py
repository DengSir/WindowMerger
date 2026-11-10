# -*- coding: utf-8 -*-
"""自动更新边界回归（假 GitHub API，共享 tools/lib/fake_gh_api.py；断言手段复用
update_e2e 的 UIA 探针）：
  U1 tag="v9.9.9-beta.1+a242d884" → 数字前缀 9.9.9 判新 → Available（按钮现身）
  U2 确认框取消 → 留在 Available：PID 不变、按钮仍在、0 次 zip 请求、通知"已取消更新"
  U3 tag="release-2.0"（解析失败）→ 绝不更新（安全属性）：API 被请求但按钮保持隐藏
  U4 tag="v0.0.0"（不比当前新）→ 无更新
  U5 releases 404（仓库无 Release）→ NoRelease → 无更新
  U6 资产名不带 -win-x64.zip（异常发布物）→ 按无更新
  U7 config CheckUpdates=false → 8s 内 0 次 API 请求（_checkUpdates 守卫）
  U8 主题菜单 ToggleCheckUpdates 翻转并持久化（false → 落盘 true）
  U9 zip 缺 WindowMerger.exe entry → 换装失败：Closing 取消、宿主保留、"安装更新失败"
  U10 .old 被占用 → 启动清理重试自愈：句柄释放后 ≤8s 内被删
用法: uv run tools\\tests\\update_edge_test.py [--exe 路径]
警告: 强杀所有 WindowMerger + 临时改 config（结束恢复缺省）。
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm
import wm_uia
from fake_gh_api import FakeGitHubApi, zip_bytes
from update_e2e_test import (cancel_update_dialog, find_update_dialog,
                             update_button_hidden, update_button_name,
                             wait_phase, wait_update_dialog)

EXE_ASSET = "WindowMerger-9.9.9-win-x64.zip"


def kill_hosts() -> None:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    for p in wm.pids_by_name("WindowMerger"):
        wm.force_kill_pid(p)
    time.sleep(0.3)


def launch(exe: str, api: FakeGitHubApi, *, strip_off: bool = True) -> int:
    env = {k: v for k, v in os.environ.items() if k != "WM_UPDATE_OFF"} if strip_off \
        else wm.host_env()
    env["WM_UPDATE_API"] = f"http://127.0.0.1:{api.port}/releases/latest"
    subprocess.Popen([exe], env=env)
    time.sleep(1.5)
    hwnds = wm.host_hwnds()
    return hwnds[0] if hwnds else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []
    exe_bytes = Path(a.exe).read_bytes()

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    kill_hosts()
    api = FakeGitHubApi()
    api.start()

    try:
        # ---------- U1 前缀解析（v+预发布段+hash）→ Available ----------
        api.configure(tag="v9.9.9-beta.1+a242d884",
                      assets=[(EXE_ASSET, zip_bytes({"WindowMerger.exe": exe_bytes}))])
        hm = launch(a.exe, api)
        if not hm:
            check("U1_AVAILABLE", False, "no host")
        else:
            check("U1_AVAILABLE", wait_phase(hm, "发现新版本", 15),
                  f"name={update_button_name(hm)!r}")

            # ---------- U2 确认框取消（检查发现即自动弹出，无需点按钮）----------
            dlg = wait_update_dialog(hm, 10)
            if not dlg:
                check("U2_CANCEL", False, "no dialog")
            else:
                de = wm_uia.element_from_handle(dlg)
                wm_uia.invoke(wm_uia.find_by_automation_id(de, "UpdateCancel"))
                time.sleep(1.0)
                pid0 = wm.pid_of(hm)
                st = wm_uia.status_text(hm) or ""
                check("U2_CANCEL", (wm.pid_of(hm) == pid0
                                    and not update_button_hidden(hm)
                                    and api.zip_hits == 0
                                    and "已取消更新" in st),
                      f"hidden={update_button_hidden(hm)} zip_hits={api.zip_hits} "
                      f"status={st!r}")
        kill_hosts()

        # ---------- U3 解析失败的 tag 绝不更新 ----------
        api.api_hits = api.zip_hits = 0
        api.configure(tag="release-2.0", assets=[])
        hm = launch(a.exe, api)
        time.sleep(8)
        check("U3_BAD_TAG_NO_UPDATE",
              bool(hm) and api.api_hits >= 1 and update_button_hidden(hm),
              f"api_hits={api.api_hits} hidden={update_button_hidden(hm) if hm else '?'}")
        kill_hosts()

        # ---------- U4 相等/更旧版本无更新 ----------
        api.configure(tag="v0.0.0", assets=[])
        hm = launch(a.exe, api)
        time.sleep(8)
        check("U4_OLD_TAG_NO_UPDATE", bool(hm) and update_button_hidden(hm))
        kill_hosts()

        # ---------- U5 404 → NoRelease ----------
        api.configure(status=404)
        hm = launch(a.exe, api)
        time.sleep(8)
        check("U5_404_NO_UPDATE", bool(hm) and update_button_hidden(hm))
        kill_hosts()

        # ---------- U6 资产名不匹配 → 按无更新 ----------
        api.configure(tag="v9.9.9", assets=[("foo.zip", b"x")])
        hm = launch(a.exe, api)
        time.sleep(8)
        check("U6_NO_MATCHING_ASSET", bool(hm) and update_button_hidden(hm))
        kill_hosts()

        # ---------- U7 CheckUpdates=false 不查 ----------
        wm.remove_config()
        wm.save_config({"CheckUpdates": False})
        api.configure(tag="v9.9.9",
                      assets=[(EXE_ASSET, zip_bytes({"WindowMerger.exe": exe_bytes}))])
        api.api_hits = 0
        hm = launch(a.exe, api)
        time.sleep(8)
        check("U7_CHECK_OFF_NO_REQUEST", bool(hm) and api.api_hits == 0,
              f"api_hits={api.api_hits}")

        # ---------- U8 菜单翻转 CheckUpdates 并持久化 ----------
        el = wm_uia.element_from_handle(hm)
        import uiautomation as auto
        theme_btn = None
        for b in [c for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=6)
                  if c.ControlTypeName == "ButtonControl"]:
            if (b.HelpText or "").startswith("主题"):
                theme_btn = b
                break
        if theme_btn is None:
            check("U8_TOGGLE_PERSIST", False, "no theme button")
        else:
            wm_uia.invoke(theme_btn)
            time.sleep(0.8)
            item = wm_uia.find_by_automation_id(el, "ToggleCheckUpdates")
            if item is None:
                # 菜单是独立弹层（all_windows_of_pid 才能走到）
                item = None
                for h in wm.all_windows_of_pid(wm.pid_of(hm)):
                    try:
                        item = wm_uia.find_by_automation_id(
                            wm_uia.element_from_handle(h), "ToggleCheckUpdates")
                    except Exception:
                        continue
                    if item is not None:
                        break
            if item is None:
                check("U8_TOGGLE_PERSIST", False, "no ToggleCheckUpdates item")
            else:
                wm_uia.invoke(item)
                time.sleep(0.8)
                wm.post_close(hm)
                time.sleep(2.0)
                try:
                    cfg = wm.load_config()
                except Exception:
                    cfg = {}
                check("U8_TOGGLE_PERSIST", cfg.get("CheckUpdates") is True,
                      f"config={cfg.get('CheckUpdates')}")
        kill_hosts()

        # ---------- U9 坏 zip → 换装失败宿主保留 ----------
        api.configure(tag="v9.9.9", assets=[(EXE_ASSET,
                                             zip_bytes({"readme.txt": b"not an exe"}))])
        hm = launch(a.exe, api)
        if not hm:
            check("U9_BAD_ZIP", False, "no host")
        else:
            check("U9A_AVAILABLE", wait_phase(hm, "发现新版本", 15))
            pid0 = wm.pid_of(hm)
            dlg = wait_update_dialog(hm, 10)  # 发现即自动弹出，直接确认走坏 zip 失败路径
            if not dlg:
                check("U9B_INSTALL_FAIL", False, "no dialog")
            else:
                wm_uia.invoke(wm_uia.find_by_automation_id(
                    wm_uia.element_from_handle(dlg), "UpdateConfirm"))
                time.sleep(6)  # 下载 + Closing 换装失败路径
                st = wm_uia.status_text(hm) or ""
                check("U9B_INSTALL_FAIL",
                      wm.pid_of(hm) == pid0 and wm.is_window_visible(hm)
                      and "安装更新失败" in st,
                      f"pid_same={wm.pid_of(hm) == pid0} status={st!r}")
        kill_hosts()

        # ---------- U10 .old 占用 → 重试清理自愈 ----------
        old_file = Path(str(a.exe) + ".old")
        old_file.write_bytes(b"stale")
        handle = open(old_file, "rb")  # 无 FILE_SHARE_DELETE → 宿主删不掉
        hm = launch(a.exe, api, strip_off=False)
        time.sleep(3.0)
        held_ok = old_file.exists()  # 占用期间删不掉（重试在跑）
        handle.close()
        gone = wm.wait_until(lambda: not old_file.exists(), 8000, 300)
        check("U10_OLD_OCCUPIED_RETRY", held_ok and gone and bool(hm),
              f"held={held_ok} gone={gone}")
        if old_file.exists():
            old_file.unlink(missing_ok=True)
        kill_hosts()
    finally:
        api.shutdown()
        kill_hosts()
        wm.remove_config()

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
