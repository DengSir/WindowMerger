# -*- coding: utf-8 -*-
r"""托盘行为靶窗：收到关闭（WM_DELETE_WINDOW，即点 X / WM_CLOSE）时**隐藏自己而不销毁**，
进程与句柄保持存活——模拟微信/QQ/Telegram 类"关闭时隐藏到托盘"应用的真实行为。
供 attach_heal_test H8 等测试验证宿主对"子窗口自隐藏"的释放语义（区别于测试脚本
从外部直接 SW_HIDE：这里的隐藏由靶窗自己的关闭处理发起，走完整托盘链路）。
用法: uv run tools/targets/tray_target.py [--geometry 420x320+80+80]
"""
import argparse
import tkinter as tk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry", default="420x320+80+80", help="WxH+X+Y（物理像素）")
    a = ap.parse_args()
    root = tk.Tk()
    root.title("WM_TRAY_TARGET")
    root.geometry(a.geometry)
    # 托盘应用的核心行为：关闭 = 隐藏，不退出进程（点托盘图标可再唤回，此处由测试
    # 以 ShowWindow 模拟"用户点托盘图标"）
    root.protocol("WM_DELETE_WINDOW", root.withdraw)
    root.mainloop()


if __name__ == "__main__":
    main()
