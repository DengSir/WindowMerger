using System.Diagnostics;
using System.IO;
using System.Windows;

namespace WindowMerger;

// ---------- 吸附编排（CLI/选择器/拖入 → TryAttach；释放/交换/替换） ----------

public sealed partial class HostWindow : Window
{
    /// <summary>
    /// 命令行吸附：WindowMerger.exe [左进程名|左PID] [右进程名|右PID]，Loaded 后执行一次。
    /// 参数为纯数字时按 PID 匹配（脚本 Start-Process -PassThru 可直接拿到），否则按进程名
    /// （可带可不带 .exe，大小写不敏感）；--left-exe/--right-exe 提供目标 exe 完整路径：
    /// 名字/PID 匹配不到时先按镜像路径匹配已运行窗口，仍没有就拉起该 exe 并轮询窗口出现
    /// （上限 12 秒，异步等待不阻塞 UI）——快捷方式双击复现组合时目标应用可以还没开。
    /// 同候选多窗口取面积最大的；未找到的跳过并在状态栏提示；已吸附的 hwnd 去重。
    /// --left-hwnd/--right-hwnd（snap 接管）绕开名字/PID 解析直连句柄——同进程多窗
    /// （记事本多标签、explorer 多窗）靠 PID 匹配会有歧义，句柄才能精确指定。
    /// </summary>
    private async void AttachStartupTargets(StartupOptions? opts)
    {
        if (opts is null
            || (string.IsNullOrWhiteSpace(opts.Left) && string.IsNullOrWhiteSpace(opts.Right)
                && string.IsNullOrWhiteSpace(opts.LeftExe) && string.IsNullOrWhiteSpace(opts.RightExe)
                && opts.LeftHwnd is null && opts.RightHwnd is null))
        {
            return;
        }

        try
        {
            // 直连句柄先吸（无效句柄报因跳过，不做名字解析回退）
            if (opts.LeftHwnd is long lh) AttachHwndTarget(AttachSide.Left, lh);
            if (opts.RightHwnd is long rh) AttachHwndTarget(AttachSide.Right, rh);

            var targets = new[]
            {
                (Side: AttachSide.Left, Raw: opts.Left, Exe: opts.LeftExe),
                (Side: AttachSide.Right, Raw: opts.Right, Exe: opts.RightExe),
            };

            // 先把能直接吸附的吸掉、缺失的并行拉起，再统一轮询等窗口出现
            var pending = new List<(AttachSide Side, string Exe, string Label)>();
            foreach (var (side, raw, exe) in targets)
            {
                if (string.IsNullOrWhiteSpace(raw) && string.IsNullOrWhiteSpace(exe)) continue;
                IntPtr hwnd = FindStartupTarget(raw, exe);
                if (hwnd != IntPtr.Zero)
                {
                    AttachFound(side, hwnd);
                    continue;
                }
                if (string.IsNullOrWhiteSpace(exe))
                {
                    ShowNotice($"未找到 {raw!.Trim()} 的窗口，已跳过");
                    continue;
                }
                string path = exe.Trim();
                if (!File.Exists(path))
                {
                    ShowNotice($"路径不存在：{path}，已跳过");
                    continue;
                }
                if (LaunchTarget(path))
                {
                    pending.Add((side, path, string.IsNullOrWhiteSpace(raw) ? Path.GetFileName(path) : raw.Trim()));
                }
            }

            var deadline = Environment.TickCount64 + 12_000;
            while (pending.Count > 0 && Environment.TickCount64 < deadline)
            {
                await Task.Delay(500);
                if (_handle == IntPtr.Zero || !IsLoaded) return; // 宿主已关闭，中止轮询
                for (int i = pending.Count - 1; i >= 0; i--)
                {
                    IntPtr hwnd = FindWindowByExePath(pending[i].Exe);
                    if (hwnd == IntPtr.Zero) continue;
                    AttachFound(pending[i].Side, hwnd);
                    pending.RemoveAt(i);
                }
            }
            foreach (var (_, _, label) in pending)
            {
                ShowNotice($"启动 {label} 超时（窗口未出现），已跳过");
            }
        }
        catch (Exception ex)
        {
            // async void 事件处理器：失败不上抛崩宿主，状态栏报因
            ShowNotice($"启动目标失败：{ex.Message}");
        }
    }

    /// <summary>snap 接管的直连句柄目标：句柄失效（目标已关/句柄复用）报因跳过，无名字解析。</summary>
    private void AttachHwndTarget(AttachSide side, long hwnd)
    {
        IntPtr h = new(hwnd);
        if (!Native.IsWindow(h))
        {
            ShowNotice($"{(side == AttachSide.Left ? "左" : "右")}: 窗口句柄无效，已跳过");
            return;
        }
        AttachFound(side, h);
    }

    /// <summary>启动目标匹配：名字/PID（raw）优先，其次按镜像路径匹配已运行窗口（exe）。</summary>
    private IntPtr FindStartupTarget(string? raw, string? exe)
    {
        IntPtr hwnd = string.IsNullOrWhiteSpace(raw) ? IntPtr.Zero : FindWindowByArg(raw.Trim());
        if (hwnd == IntPtr.Zero && !string.IsNullOrWhiteSpace(exe))
        {
            hwnd = FindWindowByExePath(exe.Trim());
        }
        return hwnd;
    }

    private void AttachFound(AttachSide side, IntPtr hwnd)
    {
        if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
        TryAttach(side, hwnd);
    }

    /// <summary>ShellExecute 拉起目标 exe（打包应用别名也能走通）；失败状态栏报因返回 false。</summary>
    private bool LaunchTarget(string path)
    {
        try
        {
            using var _ = Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            ShowNotice($"正在启动 {Path.GetFileNameWithoutExtension(path)}…");
            return true;
        }
        catch (Exception ex)
        {
            ShowNotice($"启动 {path} 失败：{ex.Message}");
            return false;
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

    /// <summary>按 exe 镜像路径匹配已运行窗口（大小写不敏感，同名/多窗口取面积最大）。
    /// pid→路径惰性查询：打不开的进程（提权/受保护）得到空路径、永不匹配。</summary>
    private IntPtr FindWindowByExePath(string exePath)
    {
        var candidates = WindowLocator.GetCandidates(_handle);
        var pidPaths = new Dictionary<uint, string>();
        return PickBestBy(candidates, c =>
        {
            if (!pidPaths.TryGetValue(c.Pid, out var path))
            {
                path = Native.GetProcessImagePath(c.Pid) ?? "";
                pidPaths[c.Pid] = path;
            }
            return path.Equals(exePath, StringComparison.OrdinalIgnoreCase);
        });
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
        // 已吸附子窗口（toolwindow）被 IsAttachable 排除，但"拖走拖回归位/拖到另一侧
        // 换侧/Ctrl 拖入替换"都以此为入口——豁免之，存活校验在 IsAttachedChild 内
        if (!IsAttachable(hwnd) && !IsAttachedChild(hwnd)) return;
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
            // 拖到另一侧 = 换到另一侧（吸附态整体搬家）：被拖子窗口当前挂在另一侧
            // 引用上（hwnd == otherHwnd），把它挂到目标侧、另一侧清空。
            // （旧赋值方向反了：side=Right 时写成 _left=_right/_right=null，被拖窗口
            // 引用直接丢失 → 孤儿停在松手位置，实测 2026-11）
            if (side == AttachSide.Left) { _left = other; _right = null; }
            else { _right = other; _left = null; }
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
