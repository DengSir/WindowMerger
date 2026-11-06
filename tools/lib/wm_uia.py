# -*- coding: utf-8 -*-
"""UI Automation 封装（comtypes）：宿主按钮 Invoke、AutomationId 查找、任务栏按钮 dump。
锁屏会话仍可用（进程内直调 Invoke，不走输入注入——AGENTS.md 实测）。

脚本导入方式同 wm.py。仅在用到 UIA 的脚本导入（依赖 comtypes，pip install comtypes）。
"""
from __future__ import annotations

import ctypes

import comtypes
import comtypes.client

# 进树先初始化 COM（comtypes 自动 CoInitialize）
_uia = None


def _automation():
    global _uia
    if _uia is None:
        # UIAutomationCore.dll 的 typelib 名是 UIAutomationClient（历史名），接口一致
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as _UIA
        # CUIAutomation CLSID
        obj = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=_UIA.IUIAutomation)
        _uia = (_UIA, obj)
    return _uia


# 属性 ID（UIAutomationClient.h）
UIA_PROCESSID_PROPERTY_ID = 30002
UIA_NAME_PROPERTY_ID = 30005
UIA_AUTOMATIONID_PROPERTY_ID = 30011
UIA_CONTROLTYPE_PROPERTY_ID = 30003
UIA_CLASSNAME_PROPERTY_ID = 30012
UIA_HELPTEXT_PROPERTY_ID = 30027

# 控件类型 ID
UIA_BUTTON_CONTROL_TYPE_ID = 50000
UIA_MENUITEM_CONTROL_TYPE_ID = 50011

# 树范围
UIA_TREE_SCOPE_CHILDREN = 2
UIA_TREE_SCOPE_DESCENDANTS = 4


def element_from_handle(hwnd: int):
    _UIA, uia = _automation()
    return uia.ElementFromHandle(ctypes.c_void_p(hwnd))


def root_element():
    _UIA, uia = _automation()
    return uia.GetRootElement()


def property_condition(prop_id: int, value):
    _UIA, uia = _automation()
    return uia.CreatePropertyCondition(prop_id, value)


def find_first(el, condition, scope: int = UIA_TREE_SCOPE_DESCENDANTS):
    return el.FindFirst(scope, condition)


def find_all(el, condition, scope: int = UIA_TREE_SCOPE_DESCENDANTS):
    return el.FindAll(scope, condition)


def find_all_buttons(el, scope: int = UIA_TREE_SCOPE_DESCENDANTS) -> list:
    """范围内全部 Button 元素（树序，与 PS AutomationElement.FindAll 一致）。"""
    cond = property_condition(UIA_CONTROLTYPE_PROPERTY_ID, UIA_BUTTON_CONTROL_TYPE_ID)
    arr = find_all(el, cond, scope)
    return [arr.GetElement(i) for i in range(arr.Length)]


def find_by_automation_id(el, automation_id: str, scope: int = UIA_TREE_SCOPE_DESCENDANTS):
    cond = property_condition(UIA_AUTOMATIONID_PROPERTY_ID, automation_id)
    return find_first(el, cond, scope)


def invoke(el) -> None:
    _UIA = _automation()[0]
    pattern = el.GetCurrentPattern(_UIA.IUIAutomationInvokePattern._iid_)
    pattern.Invoke()


def name_of(el) -> str:
    return el.CurrentName or ""


def automation_id_of(el) -> str:
    return el.CurrentAutomationId or ""


def help_text_of(el) -> str:
    return el.CurrentHelpText or ""


def bounding_rect_of(el) -> tuple[float, float, float, float]:
    """(x, y, width, height)，double 屏幕坐标。"""
    r = el.CurrentBoundingRectangle
    return (r.Left, r.Top, float(r.Width), float(r.Height))


def true_condition():
    return _automation()[1].CreateTrueCondition()


def find_all_elements(el, scope: int = UIA_TREE_SCOPE_DESCENDANTS) -> list:
    cond = true_condition()
    arr = find_all(el, cond, scope)
    return [arr.GetElement(i) for i in range(arr.Length)]


def find_all_menu_items(el, scope: int = UIA_TREE_SCOPE_DESCENDANTS) -> list:
    cond = property_condition(UIA_CONTROLTYPE_PROPERTY_ID, UIA_MENUITEM_CONTROL_TYPE_ID)
    arr = find_all(el, cond, scope)
    return [arr.GetElement(i) for i in range(arr.Length)]


def find_windows_of_pid(pid: int) -> list:
    """RootElement 直接子元素中属于该 PID 的窗口（弹层/菜单是独立顶层窗口）。"""
    cond = property_condition(UIA_PROCESSID_PROPERTY_ID, pid)
    arr = find_all(root_element(), cond, UIA_TREE_SCOPE_CHILDREN)
    return [arr.GetElement(i) for i in range(arr.Length)]


def menu_items_of_pid_windows(pid: int) -> list:
    """该进程全部顶层窗口内的 MenuItem（打开中的下拉菜单项）。"""
    items = []
    for w in find_windows_of_pid(pid):
        items.extend(find_all_menu_items(w))
    return items


def find_by_name(el, needle: str, scope: int = UIA_TREE_SCOPE_DESCENDANTS):
    """范围内第一个名字含 needle 的元素（粗匹配用；UIA 无内置 contains 条件）。"""
    for e in find_all_elements(el, scope):
        if needle in name_of(e):
            return e
    return None


def dump_taskbar_buttons() -> list[str]:
    """任务栏窗口按钮名（AutomationId 前缀 Appid: 的 Button）。UIA 检查幽灵按钮用。"""
    root = root_element()
    cond = property_condition(UIA_CLASSNAME_PROPERTY_ID, "Shell_TrayWnd")
    taskbar = find_first(root, cond, UIA_TREE_SCOPE_CHILDREN)
    if taskbar is None:
        return []
    out = []
    for b in find_all_buttons(taskbar):
        n = name_of(b)
        if n and automation_id_of(b).startswith("Appid:"):
            out.append(n)
    return out


def shell_shortcut(lnk_path: str):
    """WScript.Shell 读 .lnk（动态 IDispatch）：返回含 TargetPath/Arguments/IconLocation 的对象。"""
    return comtypes.client.CreateObject("WScript.Shell", dynamic=True).CreateShortcut(lnk_path)
