# -*- coding: utf-8 -*-
"""窗口几何持久化回归（恢复定位功能——**本测试不钉位**，恢复行为即被测对象）：
S1 保存+恢复：关→起→钉到固定矩形→优雅关（落盘）→校验 config 物理 px→再起→矩形一致
S2 最大化：最大化状态优雅关→config WinMaximized=True→再起→IsZoomed→还原→矩形=保存值
S3 屏外钳制：手工写超屏 config→再起→矩形完整落在主屏工作区（不出幽灵窗）
S4 垃圾回退：手工写 L≥R 的 config→再起→宿主存在且矩形合法（默认居中 960x600 DIP）
对应 ef15752 的五场景手工验证，首次脚本化（2026-11）。
用法: uv run tools/\tests\\geometry_persistence_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

R = (20, 80, 700, 700)  # S1/S2 固定矩形（L,T,R,B 主屏物理 px；即钉 20,80 尺寸 680x620，CI 1024 屏也放得下）


def launch(exe: str) -> int:
    subprocess.Popen([exe])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        raise SystemExit(1)
    return hm


def close_host() -> None:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    if wm.pids_by_name("WindowMerger"):
        print("HOST_DID_NOT_EXIT")
        raise SystemExit(1)


def read_cfg() -> dict:
    return wm.load_config()


def write_cfg_geo(l: float, t: float, r: float, b: float, maximized: bool = False) -> None:
    """在保留其他字段的前提下写几何四元组（宿主必须已关闭，否则关闭时会覆盖）。"""
    cfg = read_cfg()
    cfg["WinLeft"], cfg["WinTop"], cfg["WinRight"], cfg["WinBottom"] = l, t, r, b
    cfg["WinMaximized"] = maximized
    wm.save_config(cfg)


def rect_ok(hm, rect, tol=2) -> bool:
    r = wm.get_window_rect(hm)
    got = (r.Left, r.Top, r.Right, r.Bottom)
    ok = all(abs(g - e) <= tol for g, e in zip(got, rect))
    print(f"  rect={got} expect={rect} {'OK' if ok else 'MISMATCH'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    results: list[tuple[str, bool]] = []

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()

    # ---- S1: 保存 + 恢复（正常态）----
    print("S1 save+restore normal")
    hm = launch(a.exe)
    wm.set_window_pos(hm, None, R[0], R[1], R[2] - R[0], R[3] - R[1], wm.SWP_NOZORDER)
    time.sleep(1.0)
    close_host()
    cfg = read_cfg()
    geo = (cfg.get("WinLeft"), cfg.get("WinTop"), cfg.get("WinRight"), cfg.get("WinBottom"))
    s1a = all(g is not None and abs(g - e) <= 2 for g, e in zip(geo, R)) and not cfg.get("WinMaximized")
    print(f"  config geo={geo} maximized={cfg.get('WinMaximized')} {'OK' if s1a else 'MISMATCH'}")
    hm = launch(a.exe)
    s1b = rect_ok(hm, R)
    close_host()
    results.append(("S1_save_restore", s1a and s1b))

    # ---- S2: 最大化保存 + 恢复 ----
    print("S2 maximize save+restore")
    hm = launch(a.exe)  # config 里有 S1 的 R
    wm.show_window(hm, 3)  # SW_MAXIMIZE
    time.sleep(1.0)
    close_host()
    cfg = read_cfg()
    s2a = cfg.get("WinMaximized") is True
    print(f"  config WinMaximized={cfg.get('WinMaximized')} {'OK' if s2a else 'MISMATCH'}")
    hm = launch(a.exe)
    s2b = wm.is_zoomed(hm)
    print(f"  IsZoomed={s2b}")
    if s2b:
        wm.show_window(hm, 9)  # SW_RESTORE
        time.sleep(1.0)
        s2c = rect_ok(hm, R)
    else:
        s2c = False
    close_host()
    results.append(("S2_maximized", s2a and s2b and s2c))

    # ---- S3: 屏外钳制 ----
    print("S3 offscreen clamp")
    write_cfg_geo(5000, 100, 7500, 1000)  # 中心 (6250,550) → 最近屏 = 4K 主屏
    hm = launch(a.exe)
    r = wm.get_window_rect(hm)
    wa = wm.primary_work_area()
    s3 = (wa.Left <= r.Left < r.Right <= wa.Right and wa.Top <= r.Top < r.Bottom <= wa.Bottom)
    print(f"  rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) work=({wa.Left},{wa.Top})-({wa.Right},{wa.Bottom}) "
          f"{'OK' if s3 else 'OUT_OF_WORKAREA'}")
    close_host()
    results.append(("S3_offscreen_clamp", s3))

    # ---- S4: 垃圾回退（L>=R）----
    print("S4 garbage fallback")
    write_cfg_geo(500, 100, 100, 50)
    hm = launch(a.exe)
    r = wm.get_window_rect(hm)
    s4 = r.Left < r.Right and r.Top < r.Bottom
    print(f"  rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) valid={s4} (默认 960x600 DIP 居中)")
    close_host()
    results.append(("S4_garbage_fallback", s4))

    wm.remove_config()  # 还原默认配置，不残留测试几何

    print("GEOMETRY_PERSISTENCE_TEST_DONE")
    all_ok = all(ok for _, ok in results)
    for name, ok in results:
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    print(f"RESULT {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
