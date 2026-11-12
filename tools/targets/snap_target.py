# -*- coding: utf-8 -*-
"""snap 检测/接管测试靶窗：单进程单顶层无 owner 窗口，标题/几何由命令行给定。
snap_capture_test 用两个本靶进程摆出贴合布局（multi_win 的 Toplevel 是 owned 窗，
会被检测的 owner 过滤排除，不能复用）。

用法: uv run tools/targets/snap_target.py <标题> [WxH+X+Y]   （常驻直到被杀，测试负责清理）
"""
import sys
import tkinter as tk

title = sys.argv[1] if len(sys.argv) > 1 else "WM_SNAP_TARGET"
geo = sys.argv[2] if len(sys.argv) > 2 else "500x400+0+0"

root = tk.Tk()
root.title(title)
root.geometry(geo)
root.configure(bg="#3050C0")
tk.Label(root, text=title, fg="white", bg="#3050C0",
         font=("Segoe UI", 12)).pack(expand=True)
root.mainloop()
