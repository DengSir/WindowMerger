# -*- coding: utf-8 -*-
"""UI Automation 封装：宿主按钮 Invoke、AutomationId 查找、任务栏按钮 dump。
后端 = uiautomation 包（自带完整 COM 桩；comtypes 对 UIAutomation typelib 的
自动生成桩在 Python 3.14 上退化为 Incomplete，封送不可靠，勿用）。
锁屏会话仍可用（进程内直调 Invoke，不走输入注入——AGENTS.md 实测）。

脚本导入方式同 wm.py。仅在用到 UIA 的脚本导入（依赖 uiautomation/comtypes）。
"""
from __future__ import annotations

import time

import comtypes.client

import uiautomation as auto

import wm  # attach_via_panes 需要 Win32 枚举（wm 不反向依赖本模块，无环）

_SEARCH_DEPTH = 8  # WPF 视觉树不深；限制深度防大树遍历过慢


def element_from_handle(hwnd: int):
    return auto.ControlFromHandle(hwnd)


def root_element():
    return auto.GetRootControl()


def find_all_buttons(el) -> list:
    return [c for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=_SEARCH_DEPTH)
            if c.ControlTypeName == "ButtonControl"]


def find_all_menu_items(el) -> list:
    return [c for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=_SEARCH_DEPTH)
            if c.ControlTypeName == "MenuItemControl"]


def find_by_automation_id(el, automation_id: str):
    for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=_SEARCH_DEPTH):
        if c.AutomationId == automation_id:
            return c
    return None


def find_by_name(el, needle: str):
    for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=_SEARCH_DEPTH):
        if needle in (c.Name or ""):
            return c
    return None


def invoke(el) -> None:
    el.GetInvokePattern().Invoke()


def attach_via_panes(host_hwnd: int, targets: list[tuple[int, str]]) -> list[int]:
    """逐格经选择器吸附（Invoke 空格提示 _paneHint<N> → picker 过滤/选行 → 吸附按钮）。
    targets = [(pane, 过滤词), ...]（过滤词匹配窗口标题或进程名，大小写不敏感；
    merge 名字吸附退役后 = 测试搭吸附环境的统一入口，UIA 路径锁屏可用）。
    返回机械步骤全成功的 pane 清单；中途失败即止（已完成的格保留），吸附断言由调用方做。"""
    done: list[int] = []
    for pane, needle in targets:
        el = element_from_handle(host_hwnd)
        hint = find_by_automation_id(el, f"_paneHint{pane}")
        if hint is None:
            break
        try:
            invoke(hint)
        except Exception:
            break
        picker = _wait_picker(host_hwnd)
        if picker is None:
            break
        try:
            edit = _first_of_type(picker, "EditControl")
            if edit is not None:
                set_value(edit, needle)
                time.sleep(0.4)
            row = _first_of_type(picker, "ListItemControl") \
                or _first_of_type(picker, "DataItemControl")
            if row is None:
                _invoke_named(picker, "取消")
                break
            row.GetSelectionItemPattern().Select()
            time.sleep(0.3)
            ok_btn = find_by_name(picker, "吸附")
            if ok_btn is None:
                _invoke_named(picker, "取消")
                break
            invoke(ok_btn)
            time.sleep(1.2)  # 吸附 + 布局收敛
            done.append(pane)
        except Exception:
            _invoke_named(picker, "取消")
            break
    return done


def _wait_picker(host_hwnd: int, timeout_ms: int = 4000):
    """找选择器对话框 = 同 PID 可见顶层窗标题含「选择吸附到」（UIA root children 会漏
    ShowDialog owned 窗，走 Win32 枚举——picker_attach 实测）。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for h in wm.all_windows_of_pid(wm.pid_of(host_hwnd)):
            if h != host_hwnd and "选择吸附到" in wm.get_text(h, 48):
                return element_from_handle(h)
        time.sleep(0.15)
    return None


def _first_of_type(el, type_name: str):
    for c, _ in auto.WalkControl(el, includeTop=False, maxDepth=_SEARCH_DEPTH + 2):
        if c.ControlTypeName == type_name:
            return c
    return None


def _invoke_named(el, name: str) -> None:
    btn = find_by_name(el, name)
    if btn is not None:
        invoke(btn)


def status_text(hwnd: int) -> str | None:
    """宿主状态栏文案（TextBlock x:Name=_status → WPF AutomationId 回退到 x:Name）。
    找不到（UIA 瞬态错误/树未就绪）返回 None，由调用方重试。"""
    try:
        el = element_from_handle(hwnd)
        t = find_by_automation_id(el, "_status")
    except Exception:
        return None
    return None if t is None else name_of(t)


def set_value(el, text: str) -> bool:
    """ValuePattern 写入（picker 过滤框等 Edit 控件）。不支持该模式返回 False。"""
    try:
        el.GetValuePattern().SetValue(text)
        return True
    except Exception:
        return False


def name_of(el) -> str:
    return el.Name or ""


def automation_id_of(el) -> str:
    return el.AutomationId or ""


def help_text_of(el) -> str:
    return el.HelpText or ""


def bounding_rect_of(el) -> tuple[float, float, float, float]:
    """(x, y, width, height)，屏幕坐标。（uiautomation 的 RECT 字段为小写且
    width/height 是方法，不能直接调用——用 right/bottom 差值算）"""
    r = el.BoundingRectangle
    return (float(r.left), float(r.top), float(r.right - r.left), float(r.bottom - r.top))


def find_windows_of_pid(pid: int) -> list:
    """桌面根的直接子元素中属于该 PID 的窗口（弹层/菜单是独立顶层窗口）。"""
    return [c for c in root_element().GetChildren() if c.ProcessId == pid]


def menu_items_of_pid_windows(pid: int) -> list:
    """该进程全部顶层窗口内的 MenuItem（打开中的下拉菜单项）。
    顶层窗口走 Win32 枚举：UIA root children 会漏 owned 弹层（菜单/对话框，实测）。"""
    import wm as _wm
    items = []
    for h in _wm.all_windows_of_pid(pid):
        items.extend(find_all_menu_items(element_from_handle(h)))
    return items


def taskbar():
    """Shell_TrayWnd 任务栏控件；找不到 None。"""
    for c in root_element().GetChildren():
        if c.ClassName == "Shell_TrayWnd":
            return c
    return None


def dump_taskbar_buttons() -> list[str]:
    """任务栏窗口按钮名（AutomationId 前缀 Appid: 的 Button）。UIA 检查幽灵按钮用。"""
    tb = taskbar()
    if tb is None:
        return []
    out = []
    for b in find_all_buttons(tb):
        n = name_of(b)
        if n and automation_id_of(b).startswith("Appid:"):
            out.append(n)
    return out


def shell_shortcut(lnk_path: str):
    """WScript.Shell 读 .lnk（动态 IDispatch）：返回含 TargetPath/Arguments/IconLocation 的对象。"""
    return comtypes.client.CreateObject("WScript.Shell", dynamic=True).CreateShortcut(lnk_path)
