# -*- coding: utf-8 -*-
"""配置边界回归（黑盒——config.json 各写坏法 × 启动行为）：
  S1 损坏 JSON → 不崩、回退默认值，优雅关后被重写为合法默认配置（Config.cs 回退分支）
  S2 空对象 / null / 含旧版未知字段（Width/Height）→ 同样按字段默认值工作
  S3 Ratio 超界（0.05 / 0.95）→ 钳制到 [0.2, 0.8]，优雅关后落盘值即钳后值
  S4 保存几何过小（< MinWidth 400 × MinHeight 300 DIP）→ 恢复时钳到最小尺寸且完整在屏内
  S5 非法 Theme 字符串 → 回退 Auto（跟随系统深浅色），优雅关后重写为 "Auto"
每场景独立启动一次宿主（配置在启动时读取），优雅关即写回 config——断言以此为准。
用法: uv run tools\\tests\\config_edge_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad（mspaint 不动）。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia

EMPTY_HINT = "把任意窗口拖进来吸附"


def start_host(exe: str, wait: float = 4.0) -> int:
    subprocess.Popen([exe], env=wm.host_env())
    time.sleep(wait)
    hm = wm.host_hwnd()
    if not hm:
        print("FAIL_NO_HOST")
    return hm


def close_and_read_config(hm: int, wait: float = 2.0) -> dict | None:
    """优雅关（保存配置 + 正常退出）→ 回读落盘 config；进程没退/无文件返回 None。"""

    def gone() -> bool:
        return not wm.pids_by_name("WindowMerger")

    if hm:
        wm.post_close(hm)
    if not wm.wait_until(gone, 8000, 200):
        wm.force_kill_by_name("WindowMerger")
        return None
    time.sleep(wait)
    try:
        return wm.load_config()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger", "Notepad")
    time.sleep(0.5)

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    # ---------- S1 损坏 JSON ----------
    Path(wm.config_path()).write_text('{"Ratio": 0.7,,,', encoding="utf-8")
    hm = start_host(a.exe)
    alive = bool(hm)
    check("S1A_CORRUPT_ALIVE", alive)
    if hm:
        try:
            st = wm_uia.status_text(hm)
        except Exception:
            st = None
        check("S1B_EMPTY_HINT", bool(st and EMPTY_HINT in st), f"status={st!r}")
        cfg = close_and_read_config(hm)
        check("S1C_REWRITTEN_DEFAULT",
              bool(cfg) and abs(float(cfg.get("Ratio", -1)) - 0.5) < 1e-9
              and cfg.get("Theme") == "Auto" and cfg.get("CheckUpdates") is True,
              f"cfg={cfg}")

    # ---------- S2 空对象 / null / 未知字段 ----------
    for tag, blob in (("EMPTY_OBJ", "{}"), ("NULL", "null"),
                      ("LEGACY_FIELDS", '{"Width": 999, "Height": 666, "Unknown": 1}')):
        Path(wm.config_path()).write_text(blob, encoding="utf-8")
        hm = start_host(a.exe, 3.5)
        check(f"S2_{tag}_ALIVE", bool(hm))
        if hm:
            cfg = close_and_read_config(hm)
            check(f"S2_{tag}_DEFAULT",
                  bool(cfg) and abs(float(cfg.get("Ratio", -1)) - 0.5) < 1e-9
                  and cfg.get("Theme") == "Auto",
                  f"cfg={cfg}")

    # ---------- S3 Ratio 钳制 ----------
    for tag, ratio, expect in (("LOW", 0.05, 0.2), ("HIGH", 0.95, 0.8)):
        wm.remove_config()
        wm.save_config({"Ratio": ratio})
        hm = start_host(a.exe, 3.5)
        if not hm:
            check(f"S3_{tag}_ALIVE", False)
            continue
        check(f"S3_{tag}_ALIVE", True)
        cfg = close_and_read_config(hm)
        got = float(cfg.get("Ratio", -1)) if cfg else -1
        check(f"S3_{tag}_CLAMPED", abs(got - expect) < 1e-9, f"ratio={got} expect={expect}")

    # ---------- S4 保存几何过小 → 恢复钳到最小尺寸 ----------
    wm.remove_config()
    wm.save_config({"WinLeft": 100, "WinTop": 100, "WinRight": 180, "WinBottom": 140})
    hm = start_host(a.exe, 3.5)
    if not hm:
        check("S4_ALIVE", False)
    else:
        check("S4_ALIVE", True)
        r = wm.get_window_rect(hm)
        scale = wm.get_dpi_for_window(hm) / 96.0
        wa = wm.pick_test_monitor().rcWork
        size_ok = (r.width >= 400 * scale - 2 and r.height >= 300 * scale - 2)
        inside = (r.Left >= wa.Left and r.Top >= wa.Top
                  and r.Right <= wa.Right and r.Bottom <= wa.Bottom)
        check("S4_MIN_SIZE", size_ok, f"rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) "
              f"scale={scale} expect ≥{round(400 * scale)}x{round(300 * scale)}")
        check("S4_ON_SCREEN", inside)
        close_and_read_config(hm)

    # ---------- S5 非法 Theme → Auto ----------
    wm.remove_config()
    wm.save_config({"Theme": "Bogus"})
    hm = start_host(a.exe, 3.5)
    if not hm:
        check("S5_ALIVE", False)
    else:
        check("S5_ALIVE", True)
        cfg = close_and_read_config(hm)
        check("S5_THEME_AUTO", bool(cfg) and cfg.get("Theme") == "Auto", f"cfg={cfg}")

    # 还原干净状态（后续测试约定 config 存在且为默认）
    wm.remove_config()

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
