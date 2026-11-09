# -*- coding: utf-8 -*-
"""同名进程双窗靶（pid_fallback_test 用）：一个进程两个顶层窗口，
小窗 500x300、大窗 800x500——CLI 按 PID/进程名匹配时 PickBestBy 应取面积最大者。"""
import tkinter as tk

root = tk.Tk()
root.title("WM_MULTI_SMALL")
root.geometry("500x300+40+40")
big = tk.Toplevel(root)
big.title("WM_MULTI_BIG")
big.geometry("800x500+120+120")
tk.Label(root, text="SMALL 500x300").pack(expand=True)
tk.Label(big, text="BIG 800x500").pack(expand=True)
root.mainloop()
