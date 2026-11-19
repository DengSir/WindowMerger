using System.Windows;
using System.Windows.Threading;

namespace WindowMerger;

// ---------- 吸附编排（CLI/选择器/拖入 → TryAttach；释放/替换/换格） ----------

public sealed partial class HostWindow : Window
{
    /// <summary>
    /// snap 接管宿主的启动吸附：种子里的 pane 序句柄 i → 格 i（检测输出的布局格序），
    /// Loaded 后执行一次。无效句柄（检测到吸附之间目标退出的竞态）报因跳过。
    /// 名字/PID 解析与 exe 拉起已随 merge 子命令退役——单进程直开后句柄来自检测，天然精确。
    /// </summary>
    private void AttachStartupTargets(StartupOptions? opts)
    {
        TracePoint("AttachStartupTargets enter (Loaded)");
        if (opts?.PaneHwnds is not { Count: > 0 } hwnds) return;
        for (int i = 0; i < hwnds.Count; i++)
            AttachHwndTarget(i, hwnds[i]);

        // 任务栏按钮图标加固：按钮由 shell 在窗口可见后才异步创建，Loaded 帧内连续三次
        // WM_SETICON（fallback→占位拼图→多窗拼图）可能撞上按钮创建竞态被吞——
        // 空闲优先级再断言一次最终态（幂等重设；运行中路径的 UpdateHostIcon 不走这里）
        _ = Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle,
            new Action(() => UpdateHostIcon("IdleReassert")));
    }

    /// <summary>接管宿主的直连句柄目标：句柄失效（目标已关/句柄复用）报因跳过。</summary>
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

    private void AttachFound(int pane, IntPtr hwnd)
    {
        Native.RestoreIfMinimized(hwnd);
        TryAttach(pane, hwnd);
    }

    internal bool IsAttachable(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || hwnd == _handle) return false;
        if (!Native.IsWindow(hwnd) || !Native.IsWindowVisible(hwnd) || Native.IsIconic(hwnd)) return false;
        if (Native.IsCloaked(hwnd)) return false;
        if (Native.HasExStyle(hwnd, Native.WindowExStyles.ToolWindow)) return false;
        if (Native.GetRelatedWindow(hwnd, Native.GetWindowRelation.Owner) != IntPtr.Zero) return false;
        if (App.OwnsAttachedChildByOther(hwnd, this)) return false; // 另一宿主的吸附子窗：不亮框不进候选
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
        // 目标格必须存在于当前布局：接管种子句柄数与格数不符（理论不可达，防御性）时跳过
        if (pane < 0 || pane >= _panes.Length)
        {
            ShowNotice($"{(pane >= 0 ? $"第 {pane + 1} 格" : "目标格")}超出当前布局（{_layout.ConfigName}），已跳过");
            return;
        }
        // 已吸附子窗口（toolwindow）被 IsAttachable 排除，但"拖走拖回归位/拖到其他格
        // 换格/Ctrl 拖入替换"都以此为入口——豁免之，存活校验在 IsAttachedChild 内
        if (!IsAttachable(hwnd) && !IsAttachedChild(hwnd)) return;
        // 跨宿主抢窗卡点：已被另一宿主吸附的窗口不收——两只宿主的 250ms 维护定时器会
        // 互相拉扯同一批窗口（ApplyLayout/FixZOrder/DeleteTab 断言互覆）。本宿主自己的
        // 子窗（归位/换格）放行——IndexOfChildHwnd >= 0 已区分
        if (IndexOfChildHwnd(hwnd) < 0 && App.OwnsAttachedChildByOther(hwnd, this))
        {
            TracePoint($"TryAttach pane={pane} hwnd={hwnd.ToInt64():X} 已被另一宿主接管，拒绝");
            ShowNotice("该窗口已被另一宿主接管，先在原宿主释放再吸附");
            return;
        }
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
