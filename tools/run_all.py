# -*- coding: utf-8 -*-
"""一键完整回归：按依赖顺序跑全部自动测试，汇总 PASS/FAIL/SKIP 表。
SKIP 判定 = 脚本 exit 0 且输出含 SKIP_；判定 = 尾部 RESULT PASS/FAIL 行 + exit code。
用法: uv run tools/\run_all.py [--only 名称,名称] [--list]
警告: 测试会无差别关闭所有 WindowMerger/Notepad/mspaint——包括你自己开着的实例。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

# 依赖顺序：run_test_flow 留下的吸附组合给 release_test 用；其余各自清理
TESTS = [
    ("run_test_flow",       TOOLS / "tests" / "run_test_flow.py",            120),
    ("release_test",        TOOLS / "tests" / "release_test.py",              60),
    ("picker_attach_test",  TOOLS / "tests" / "picker_attach_test.py",        90),
    ("swap_sides_test",     TOOLS / "tests" / "swap_sides_test.py",           90),
    ("pid_mode_test",       TOOLS / "tests" / "pid_mode_test.py",             90),
    ("exclude_self_test",   TOOLS / "tests" / "exclude_self_test.py",         90),
    ("shortcut_create_test", TOOLS / "tests" / "shortcut_create_test.py",     90),
    ("launch_attach_test",  TOOLS / "tests" / "launch_attach_test.py",        90),
    ("orphan_e2e_test",     TOOLS / "tests" / "orphan_e2e_test.py",           90),
    ("geometry_persistence_test", TOOLS / "tests" / "geometry_persistence_test.py", 150),
    ("cursor_drop_test",    TOOLS / "tests" / "cursor_drop_test.py",          90),
    ("covered_drag_test",   TOOLS / "tests" / "covered_drag_test.py",         90),
    ("maximize_drag_test",  TOOLS / "tests" / "maximize_drag_test.py",        90),
    ("double_click_max_test", TOOLS / "tests" / "double_click_max_test.py",   90),
    ("divider_resize_test", TOOLS / "tests" / "divider_resize_test.py",       90),
    ("minimize_linkage_test", TOOLS / "tests" / "minimize_linkage_test.py",   90),
    ("drag_switch_side_test", TOOLS / "tests" / "drag_switch_side_test.py",   90),
    ("cross_dpi_seam_test", TOOLS / "tests" / "cross_dpi_seam_test.py",       90),
    ("alt_tab_z_repro",     TOOLS / "tests" / "alt_tab_z_repro.py",          120),
    ("ghost_cycle_test",    TOOLS / "tests" / "ghost_cycle_test.py",         300),
    ("theme_menu_test",     TOOLS / "visual" / "theme_menu_test.py",          90),
    ("theme_toggle_visual_test", TOOLS / "visual" / "theme_toggle_visual_test.py", 90),
    ("tooltip_shot",        TOOLS / "visual" / "tooltip_shot.py",            120),
    ("hover_visual_test",   TOOLS / "visual" / "hover_visual_test.py",        90),
    ("divider_hover_test",  TOOLS / "visual" / "divider_hover_test.py",       90),
    ("hint_pane_shot",      TOOLS / "visual" / "hint_pane_shot.py",          120),
    ("pick_btn_dump",       TOOLS / "visual" / "pick_btn_dump.py",            90),
    ("glyph_verify",        TOOLS / "visual" / "glyph_verify.py",             90),
    ("side_btn_shot",       TOOLS / "visual" / "side_btn_shot.py",            90),
    ("top_bar_left_shot",   TOOLS / "visual" / "top_bar_left_shot.py",        90),
    ("icon_verify",         TOOLS / "visual" / "icon_verify.py",              90),
    ("theme_menu_shot",     TOOLS / "visual" / "theme_menu_shot.py",          90),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔的测试名子集")
    ap.add_argument("--list", action="store_true", help="只列出测试清单")
    a = ap.parse_args()

    tests = TESTS
    if a.only:
        names = {n.strip() for n in a.only.split(",") if n.strip()}
        tests = [t for t in TESTS if t[0] in names]
        missing = names - {t[0] for t in tests}
        if missing:
            print(f"UNKNOWN: {', '.join(sorted(missing))}")
            return 1
    if a.list:
        for name, path, _ in tests:
            print(name)
        return 0

    rows: list[tuple[str, str, float, str]] = []  # (名称, 状态, 秒, 结果行)
    for i, (name, path, timeout) in enumerate(tests, 1):
        print(f"\n===== [{i}/{len(tests)}] {name} =====")
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, str(path)],  # uv run 入口下 = venv 解释器，子进程同环境
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout)
            out = proc.stdout + proc.stderr
            status = "PASS" if proc.returncode == 0 else "FAIL"
            if proc.returncode == 0 and "SKIP" in out:
                status = "SKIP"
            tail = [ln for ln in out.strip().splitlines() if ln.startswith("RESULT")]
            verdict = tail[-1] if tail else out.strip().splitlines()[-1] if out.strip() else "(no output)"
        except subprocess.TimeoutExpired:
            out = ""
            status, verdict = "FAIL", f"TIMEOUT ({timeout}s)"
        secs = time.monotonic() - start
        # 流式回显脚本输出（缩进）
        for ln in out.strip().splitlines():
            print(f"  | {ln}")
        rows.append((name, status, secs, verdict))

    print("\n===== SUMMARY =====")
    n_pass = n_fail = n_skip = 0
    for name, status, secs, verdict in rows:
        mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "◌"}[status]
        print(f"{mark} {status:<4} {name:<28} {secs:5.1f}s  {verdict}")
        n_pass += status == "PASS"
        n_fail += status == "FAIL"
        n_skip += status == "SKIP"
    print(f"\n{len(rows)} tests: {n_pass} PASS, {n_fail} FAIL, {n_skip} SKIP")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
