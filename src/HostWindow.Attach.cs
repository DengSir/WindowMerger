using System.Diagnostics;
using System.Windows;

namespace WindowMerger;

// ---------- 吸附编排（CLI/选择器/拖入 → TryAttach；释放/交换/替换） ----------

public sealed partial class HostWindow : Window
{
    /// <summary>
    /// 命令行吸附：WindowMerger.exe [左进程名|左PID] [右进程名|右PID]，Loaded 后执行一次。
    /// 参数为纯数字时按 PID 匹配（脚本 Start-Process -PassThru 可直接拿到），否则按进程名
    /// （可带可不带 .exe，大小写不敏感）；同候选多窗口取面积最大的；
    /// 未找到的跳过并在状态栏提示；已吸附的 hwnd 去重。
    /// </summary>
    private void AttachStartupTargets(string? cliLeft, string? cliRight)
    {
        if (cliLeft is null && cliRight is null) return;

        var targets = new[]
        {
            (Side: AttachSide.Left, Raw: cliLeft),
            (Side: AttachSide.Right, Raw: cliRight),
        };
        foreach (var (side, raw) in targets)
        {
            if (string.IsNullOrWhiteSpace(raw)) continue;
            string arg = raw.Trim();

            IntPtr hwnd = FindWindowByArg(arg);
            if (hwnd == IntPtr.Zero)
            {
                ShowNotice($"未找到 {arg} 的窗口，已跳过");
                continue;
            }
            if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
            TryAttach(side, hwnd);
        }
    }

    /// <summary>按命令行参数找窗口：纯数字 = PID，否则 = 进程名（可带 .exe 后缀）。同候选多窗口取面积最大。
    /// PID 匹配三级回退：精确 PID → 该进程的后代进程树（Win11 打包应用经别名 stub 拉起，
    /// Start-Process -PassThru 返回的 stub 没有窗口，真实窗口属于其后代进程）→ 同名进程（stub
    /// 已退出时树仍可走而名字查询不行，故名字放最后兜底单实例交接场景）。</summary>
    private IntPtr FindWindowByArg(string arg)
    {
        bool byPid = long.TryParse(arg, out var pid);
        string name = arg;
        if (!byPid && name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) name = name[..^4];

        var candidates = WindowLocator.GetCandidates(_handle);
        IntPtr best = PickBestBy(candidates, c =>
            byPid ? c.Pid == pid : c.ProcessName.Equals(name, StringComparison.OrdinalIgnoreCase));
        if (best != IntPtr.Zero || !byPid) return best;

        // 回退 1：后代进程树（Win11 别名 stub → 真实打包应用）
        var descendants = Native.GetDescendantProcessIds((int)pid);
        best = PickBestBy(candidates, c => descendants.Contains((int)c.Pid));
        if (best != IntPtr.Zero) return best;

        // 回退 2：同名进程（stub 已退出等交接场景的最后兜底）
        try
        {
            string pname = Process.GetProcessById((int)pid).ProcessName;
            best = PickBestBy(candidates, c => c.ProcessName.Equals(pname, StringComparison.OrdinalIgnoreCase));
        }
        catch (ArgumentException)
        {
            // PID 不存在（进程已退出且无后代），保持未匹配
        }
        return best;
    }

    private IntPtr PickBestBy(IEnumerable<WindowCandidate> candidates, Func<WindowCandidate, bool> match)
    {
        IntPtr best = IntPtr.Zero;
        long bestArea = -1;
        foreach (var c in candidates)
        {
            if (!match(c)) continue;
            if (c.Hwnd == (_left?.Hwnd ?? IntPtr.Zero) || c.Hwnd == (_right?.Hwnd ?? IntPtr.Zero)) continue; // 已吸附的跳过
            if (!Native.GetWindowRect(c.Hwnd, out var r)) continue;
            long area = (long)r.Width * r.Height;
            if (area > bestArea)
            {
                bestArea = area;
                best = c.Hwnd;
            }
        }
        return best;
    }

    internal bool IsAttachable(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || hwnd == _handle) return false;
        if (!Native.IsWindow(hwnd) || !Native.IsWindowVisible(hwnd) || Native.IsIconic(hwnd)) return false;
        if (Native.IsCloaked(hwnd)) return false;
        if ((Native.GetWindowLong(hwnd, Native.GWL_EXSTYLE) & Native.WS_EX_TOOLWINDOW) != 0) return false;
        if (Native.GetWindow(hwnd, Native.GW_OWNER) != IntPtr.Zero) return false;
        uint pid = Native.GetPid(hwnd);
        if (pid == (uint)Environment.ProcessId) return false;
        return !WindowLocator.IsOtherSelf(pid, (uint)Environment.ProcessId); // 排除"另一个自己"
    }

    internal bool IsAttachedChild(IntPtr hwnd)
        => hwnd != IntPtr.Zero && (hwnd == (_left?.Hwnd ?? IntPtr.Zero) || hwnd == (_right?.Hwnd ?? IntPtr.Zero));

    /// <summary>拖放是否被允许：空格、拖回自己、或按住 Ctrl 替换。不允许则不显示高亮。</summary>
    internal bool IsDropAllowed(IntPtr hwnd, AttachSide side)
    {
        IntPtr cur = HwndOf(side);
        if (cur == IntPtr.Zero || cur == hwnd) return true;
        return IsCtrlHeld();
    }

    internal void TryAttach(AttachSide side, IntPtr hwnd)
    {
        if (!IsAttachable(hwnd)) return;
        var otherSide = side == AttachSide.Left ? AttachSide.Right : AttachSide.Left;
        var child = ChildAt(side);
        var other = ChildAt(otherSide);
        IntPtr cur = child?.Hwnd ?? IntPtr.Zero;
        IntPtr otherHwnd = other?.Hwnd ?? IntPtr.Zero;

        if (hwnd == cur)
        {
            ApplyLayoutTo(child, side); // 拖走又拖回来：吸附回原格
            return;
        }
        if (cur != IntPtr.Zero && !IsCtrlHeld())
        {
            // 占用侧默认不替换；按住 Ctrl 才允许新窗口顶掉旧的
            ShowNotice("该侧已吸附窗口：按住 Ctrl 拖入可替换");
            return;
        }
        if (hwnd == otherHwnd)
        {
            // 拖到另一侧 = 换到另一侧（吸附态整体搬家）
            if (side == AttachSide.Left) { _right = _left; _left = null; }
            else { _left = _right; _right = null; }
            ApplyLayoutTo(ChildAt(side), side);
            UpdateStatus();
            return;
        }

        if (child is not null) child.Restore(); // 替换：原窗口回到吸附前位置
        var attached = AttachedChild.Attach(_handle, hwnd);
        if (side == AttachSide.Left) _left = attached; else _right = attached;
        attached.PrepareForDock();
        if (!ApplyLayoutTo(attached, side))
        {
            // SetWindowPos 被拒：最常见是目标窗口以更高权限运行（UIPI 拦截跨完整性级别操作）
            DetachStateOnly(side, attached);
            ShowNotice("无法吸附：该窗口权限更高（以管理员身份运行 WindowMerger 可解决）");
            return;
        }
        RaiseChildrenBelow();
        UpdateStatus();
        UpdateHostIcon();
        SaveConfig(); // 吸附即落盘：宿主被强杀时孤儿清理才有 HWND 可循
    }

    /// <summary>吸附失败时只清理状态，不尝试恢复窗口几何（窗口从未被移动过）。</summary>
    private void DetachStateOnly(AttachSide side, AttachedChild child)
    {
        if (ChildAt(side) == child)
        {
            if (side == AttachSide.Left) _left = null; else _right = null;
        }
        child.Undock();
        UpdateStatus();
        UpdateHostIcon();
    }

    private void ReleaseAll()
    {
        _left?.Restore();
        _right?.Restore();
        _left = null;
        _right = null;
        UpdateStatus();
        UpdateHostIcon();
    }

    private void SwapSides()
    {
        (_left, _right) = (_right, _left);
        ApplyLayout();
        UpdateStatus();
        UpdateHostIcon();
    }

    private void Pick(AttachSide side)
    {
        var picker = new PickerWindow(side, _handle) { Owner = this };
        picker.ShowDialog();
        var result = picker.Result;
        if (picker.DialogResult == true && result is not null)
        {
            TryAttach(side, result.Hwnd);
        }
    }
}
