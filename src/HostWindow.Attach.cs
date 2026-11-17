using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Threading;

namespace WindowMerger;

// ---------- 吸附编排（CLI/选择器/拖入 → TryAttach；释放/替换/换格） ----------

public sealed partial class HostWindow : Window
{
    /// <summary>
    /// 命令行吸附：WindowMerger.exe merge [格1] [格2] [格3] [格4]（位置参数按布局格序填入），
    /// Loaded 后执行一次。参数为纯数字时按 PID 匹配（脚本 Start-Process -PassThru 可直接拿到），
    /// 否则按进程名（可带可不带 .exe，大小写不敏感）；--left-exe/--right-exe 提供目标 exe
    /// 完整路径（仅前两格）：名字/PID 匹配不到时先按镜像路径匹配已运行窗口，仍没有就拉起
    /// 该 exe 并轮询窗口出现（上限 12 秒，异步等待不阻塞 UI）——快捷方式双击复现组合时
    /// 目标应用可以还没开。同候选多窗口取面积最大的；未找到的跳过并在状态栏提示；
    /// 已吸附的 hwnd 去重。--left-hwnd/--right-hwnd（snap 接管）绕开名字/PID 解析直连句柄
    /// ——同进程多窗（记事本多标签、explorer 多窗）靠 PID 匹配会有歧义，句柄才能精确指定。
    /// </summary>
    private async void AttachStartupTargets(StartupOptions? opts)
    {
        TracePoint("AttachStartupTargets enter (Loaded)");
        if (opts is null
            || (string.IsNullOrWhiteSpace(opts.Left) && string.IsNullOrWhiteSpace(opts.Right)
                && string.IsNullOrWhiteSpace(opts.Pane2) && string.IsNullOrWhiteSpace(opts.Pane3)
                && string.IsNullOrWhiteSpace(opts.LeftExe) && string.IsNullOrWhiteSpace(opts.RightExe)
                && opts.LeftHwnd is null && opts.RightHwnd is null
                && (opts.PaneHwnds is null || opts.PaneHwnds.Count == 0)))
        {
            return;
        }

        try
        {
            // 直连句柄先吸（无效句柄报因跳过，不做名字解析回退）
            if (opts.LeftHwnd is long lh) AttachHwndTarget(0, lh);
            if (opts.RightHwnd is long rh) AttachHwndTarget(1, rh);

            // pane 序句柄（--pane-hwnds，snap 多布局接管）：句柄 i → 格 i（检测输出的
            // 布局格序）；句柄数与格数不符由 TryAttach 的"超出当前布局"守卫逐格报因跳过
            if (opts.PaneHwnds is { Count: > 0 } paneHwnds)
            {
                for (int i = 0; i < paneHwnds.Count; i++)
                    AttachHwndTarget(i, paneHwnds[i]);
            }

            // 目标按布局格序填入（--left/--right = 前 2 格的命名别名；第 3/4 格仅位置参数）
            var targets = new[]
            {
                (Pane: 0, Raw: opts.Left, Exe: (string?)opts.LeftExe),
                (Pane: 1, Raw: opts.Right, Exe: (string?)opts.RightExe),
                (Pane: 2, Raw: opts.Pane2, Exe: (string?)null),
                (Pane: 3, Raw: opts.Pane3, Exe: (string?)null),
            };

            // 先把能直接吸附的吸掉、缺失的并行拉起，再统一轮询等窗口出现
            var pending = new List<(int Pane, string Exe, string Label)>();
            foreach (var (pane, raw, exe) in targets)
            {
                if (string.IsNullOrWhiteSpace(raw) && string.IsNullOrWhiteSpace(exe)) continue;
                IntPtr hwnd = FindStartupTarget(raw, exe);
                if (hwnd != IntPtr.Zero)
                {
                    AttachFound(pane, hwnd);
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
                    pending.Add((pane, path, string.IsNullOrWhiteSpace(raw) ? Path.GetFileName(path) : raw.Trim()));
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
                    AttachFound(pending[i].Pane, hwnd);
                    pending.RemoveAt(i);
                }
            }
            foreach (var (_, _, label) in pending)
            {
                ShowNotice($"启动 {label} 超时（窗口未出现），已跳过");
            }

            // 任务栏按钮图标加固：按钮由 shell 在窗口可见后才异步创建，Loaded 帧内连续三次
            // WM_SETICON（fallback→占位拼图→多窗拼图）可能撞上按钮创建竞态被吞——
            // 空闲优先级再断言一次最终态（幂等重设；运行中路径的 UpdateHostIcon 不走这里）
            _ = Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle,
                new Action(() => UpdateHostIcon("IdleReassert")));
        }
        catch (Exception ex)
        {
            // async void 事件处理器：失败不上抛崩宿主，状态栏报因
            ShowNotice($"启动目标失败：{ex.Message}");
        }
    }

    /// <summary>snap 接管的直连句柄目标：句柄失效（目标已关/句柄复用）报因跳过，无名字解析。</summary>
    private void AttachHwndTarget(int pane, long hwnd)
    {
        IntPtr h = new(hwnd);
        if (!Native.IsWindow(h))
        {
            ShowNotice($"{PaneName(pane)}: 窗口句柄无效，已跳过");
            return;
        }
        AttachFound(pane, h);
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

    private void AttachFound(int pane, IntPtr hwnd)
    {
        if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
        TryAttach(pane, hwnd);
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
            if (IsAttachedChild(c.Hwnd)) continue; // 已吸附的跳过
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
        => hwnd != IntPtr.Zero && IndexOfChildHwnd(hwnd) >= 0;

    /// <summary>hwnd 当前挂在哪个格（未吸附返回 -1）。</summary>
    private int IndexOfChildHwnd(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return -1;
        for (int i = 0; i < _panes.Length; i++)
        {
            if (_panes[i]?.Hwnd == hwnd) return i;
        }
        return -1;
    }

    /// <summary>拖放是否被允许：空格、拖回自己、或按住 Ctrl 替换。不允许则不显示高亮。</summary>
    internal bool IsDropAllowed(IntPtr hwnd, int pane)
    {
        IntPtr cur = HwndOf(pane);
        if (cur == IntPtr.Zero || cur == hwnd) return true;
        return IsCtrlHeld();
    }

    internal void TryAttach(int pane, IntPtr hwnd)
    {
        // 目标格必须存在于当前布局：CLI 4 位置参数落在 LR 宿主（第 3/4 格不存在）时静默跳过
        if (pane < 0 || pane >= _panes.Length)
        {
            ShowNotice($"{(pane >= 0 ? $"第 {pane + 1} 格" : "目标格")}超出当前布局（{_layout.ConfigName}），已跳过");
            return;
        }
        // 已吸附子窗口（toolwindow）被 IsAttachable 排除，但"拖走拖回归位/拖到其他格
        // 换格/Ctrl 拖入替换"都以此为入口——豁免之，存活校验在 IsAttachedChild 内
        if (!IsAttachable(hwnd) && !IsAttachedChild(hwnd)) return;
        var child = ChildAt(pane);
        IntPtr cur = child?.Hwnd ?? IntPtr.Zero;

        if (hwnd == cur)
        {
            TracePoint($"TryAttach pane={pane} hwnd={hwnd.ToInt64():X} 归位（拖回原格）");
            ApplyLayoutTo(child, pane); // 拖走又拖回来：吸附回原格
            return;
        }
        if (cur != IntPtr.Zero && !IsCtrlHeld())
        {
            TracePoint($"TryAttach pane={pane} hwnd={hwnd.ToInt64():X} 占用格拒绝");
            // 占用格默认不替换；按住 Ctrl 才允许新窗口顶掉旧的
            ShowNotice("该格已吸附窗口：按住 Ctrl 拖入可替换");
            return;
        }
        int from = IndexOfChildHwnd(hwnd); // ≠ pane（hwnd != cur 已排除），-1 = 新窗口
        if (from >= 0)
        {
            // 拖到其他格 = 换格（吸附态整体搬家）：把**被拖窗口的吸附态**挂到目标格、原格
            // 清空。（2026-11 旧两格版曾因赋值方向反了丢引用 → 孤儿停在松手位置；多布局
            // 泛化时又取错变量——child 是目标格原占用者（空格=null），挂它 = 被拖窗对象
            // 丢失、窗孤儿式停在松手位置。必须从原格取被拖窗自己的吸附态）
            var dragged = _panes[from];
            TracePoint($"TryAttach pane={pane} hwnd={hwnd.ToInt64():X} 换格 from={from}");
            _panes[from] = null;
            _panes[pane] = dragged;
            if (!ApplyLayoutTo(dragged, pane))
            {
                // MOVESIZEEND hook 回调期窗口移动循环尚在收尾，SetWindowPos 瞬态被拒
                // （本地实测 100% 复现）：延迟一拍重试一次；250ms 维护定时器的 ApplyLayout
                // 仍按 _panes 持续对账兜底
                TracePoint("TryAttach 换格 placed=False，延迟重试");
                Dispatcher.BeginInvoke(System.Windows.Threading.DispatcherPriority.Background,
                    () => { if (ChildAt(pane) == dragged) ApplyLayoutTo(dragged, pane); });
            }
            UpdateStatus();
            return;
        }

        if (child is not null) child.Restore(); // 替换：原窗口回到吸附前位置
        var attached = AttachedChild.Attach(_handle, hwnd);
        _panes[pane] = attached;
        attached.PrepareForDock();
        if (!ApplyLayoutTo(attached, pane))
        {
            // SetWindowPos 被拒：最常见是目标窗口以更高权限运行（UIPI 拦截跨完整性级别操作）
            TracePoint($"TryAttach pane={pane} hwnd={hwnd.ToInt64():X} 新吸附 PlaceInPane 失败（UIPI?）");
            DetachStateOnly(pane, attached);
            ShowNotice("无法吸附：该窗口权限更高（以管理员身份运行 WindowMerger 可解决）");
            return;
        }
        RaiseChildrenBelow();
        UpdateStatus();
        UpdateHostIcon("TryAttach");
        SaveConfig(); // 吸附即落盘：宿主被强杀时孤儿清理才有 HWND 可循
    }

    /// <summary>吸附失败时只清理状态，不尝试恢复窗口几何（窗口从未被移动过）。</summary>
    private void DetachStateOnly(int pane, AttachedChild child)
    {
        if (ChildAt(pane) == child)
        {
            _panes[pane] = null;
        }
        child.Undock();
        UpdateStatus();
        UpdateHostIcon("DetachStateOnly");
    }

    private void ReleaseAll()
    {
        foreach (var child in _panes)
        {
            child?.Restore();
        }
        Array.Clear(_panes);
        UpdateStatus();
        UpdateHostIcon("ReleaseAll");
    }

    private void Pick(int pane)
    {
        var picker = new PickerWindow(PaneName(pane), _handle) { Owner = this };
        picker.ShowDialog();
        var result = picker.Result;
        if (picker.DialogResult == true && result is not null)
        {
            TryAttach(pane, result.Hwnd);
        }
    }
}
