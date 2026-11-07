# -*- coding: utf-8 -*-
"""拖动测试专用靶窗（用户提议：自写 GUI 靶，替代 Ribbon 画图）。
零 Ribbon/零 PMv2/标题条几何完全已知——把"靶程序特性"与"CI 会话特性"解耦。

用法: uv run tools/targets/drag_target.py   （由测试以子进程拉起，常驻直到被杀）
识别: 顶层窗口标题 = WM_DRAG_TARGET（FindWindowW 精确匹配）
"""
import tkinter as tk

root = tk.Tk()
root.title("WM_DRAG_TARGET")
root.geometry("500x300+0+0")
root.configure(bg="#3050C0")
tk.Label(root, text="WM_DRAG_TARGET\n拖动测试靶窗", fg="white", bg="#3050C0",
         font=("Segoe UI", 12)).pack(expand=True)
root.mainloop()
