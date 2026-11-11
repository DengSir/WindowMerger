using System.Runtime.InteropServices;
using System.Windows;

namespace WindowMerger;

/// <summary>
/// 单个已吸附子窗口的吸附态与窗口操作。不含任何左右/几何/UI 语义，
/// 可在左右格之间整体交换（SwapSides = 引用交换）。
/// 自身 hwnd 的 Win32 操作（放置/移动/样式/圆角/还原）都在这里，
/// 宿主只负责计算目标矩形与编排。
/// </summary>
internal sealed class AttachedChild
{
    private readonly IntPtr _host;  // 宿主句柄：子窗口插入点（宿主正下方）

    public IntPtr Hwnd;                                // 当前子窗口
    public uint Pid;                                   // 子窗口所属进程（孤儿清理的句柄复用校验）
    public Native.RECT PreAttachRect;                  // 吸附前矩形（释放还原用）
    private int _tabReassertCountdown = 1;             // 任务栏隐藏重断言倒计时（首个维护 tick 立即补一次）


    private AttachedChild(IntPtr host, IntPtr hwnd, uint pid)
    {
        _host = host;
        Hwnd = hwnd;
        Pid = pid;
    }

    /// <summary>吸附时捕获吸附态：吸附前矩形（最小化中则取还原矩形）+ 所属 PID。
    /// 隐形边不在此捕获——见 PlaceInPane，每次放置现场实测。</summary>
    public static AttachedChild Attach(IntPtr host, IntPtr hwnd)
    {
        Native.GetWindowThreadProcessId(hwnd, out var pid);
        var child = new AttachedChild(host, hwnd, pid);
        if (Native.IsIconic(hwnd))
        {
            var pl = new Native.WINDOWPLACEMENT { length = Marshal.SizeOf<Native.WINDOWPLACEMENT>() };
            if (Native.GetWindowPlacement(hwnd, ref pl)) child.PreAttachRect = pl.rcNormalPosition;
            else if (Native.GetWindowRect(hwnd, out var r)) child.PreAttachRect = r;
        }
        else if (Native.GetWindowRect(hwnd, out var r2))
        {
            child.PreAttachRect = r2;
        }
        return child;
    }

    /// <summary>窗口仍在且存活。</summary>
    public bool IsAlive => Hwnd != IntPtr.Zero && Native.IsWindow(Hwnd);

    /// <summary>存活且处于可放置状态（非最小化/非最大化）。</summary>
    public bool CanPlace => IsAlive && !Native.IsIconic(Hwnd) && !Native.IsZoomed(Hwnd);

    /// <summary>吸附前置：直角化 + iconic 还原 + 任务栏/Alt+Tab 隐藏（DeleteTab，不改窗口样式）。</summary>
    public void PrepareForDock()
    {
        Native.SetSquareCorners(Hwnd, square: true);
        if (Native.IsIconic(Hwnd)) Native.ShowWindow(Hwnd, Native.SW_RESTORE);
        Native.SetTaskbarTab(Hwnd, show: false);
    }

    /// <summary>解除吸附外观：圆角还原 + 任务栏收录回来（不动几何）。</summary>
    public void Undock()
    {
        Native.SetSquareCorners(Hwnd, square: false);
        Native.SetTaskbarTab(Hwnd, show: true);
    }

    /// <summary>
    /// 完整释放还原：Undock + iconic 还原 + 摘置顶污染 + 回吸附前矩形。
    /// 只碰自己的 hwnd；UIPI 失败按设计静默（与旧 DetachRestore 行为一致）。
    /// </summary>
    public void Restore()
    {
        Undock();
        if (!Native.IsWindow(Hwnd)) return;
        var r = PreAttachRect;
        if (Native.IsIconic(Hwnd)) Native.ShowWindow(Hwnd, Native.SW_RESTORE);
        // 摘除可能被外部污染的置顶标记，窗口回到普通层
        Native.SetWindowPos(Hwnd, Native.HwndNotTopmost, 0, 0, 0, 0,
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE
            | Native.SWP_NOOWNERZORDER);
        Native.SetWindowPos(Hwnd, IntPtr.Zero, r.Left, r.Top, r.Width, r.Height,
            Native.SWP_NOZORDER | Native.SWP_NOACTIVATE | Native.SWP_NOOWNERZORDER);
    }

    /// <summary>确保处于吸附位的正常可见状态：任务栏保持隐藏、非最小化/最大化、可见。</summary>
    public void EnsureDockedState()
    {
        if (!IsAlive) return;
        // DeleteTab 是 shell 侧运行时状态且无查询接口（explorer 重启会重建 task list、
        // 个别 shell 事件可能重新收录按钮）——每 ~2s 低频重断言，替代旧的样式位检查
        if (--_tabReassertCountdown <= 0)
        {
            Native.SetTaskbarTab(Hwnd, show: false);
            _tabReassertCountdown = 8; // 250ms 维护周期 × 8 ≈ 2s
        }
        if (Native.IsIconic(Hwnd) || Native.IsZoomed(Hwnd))
        {
            Native.ShowWindow(Hwnd, Native.SW_RESTORE);
        }
        else if (!Native.IsWindowVisible(Hwnd))
        {
            Native.ShowWindow(Hwnd, Native.SW_SHOWNA);
        }
    }

    /// <summary>
    /// 放进格子：外扩自身隐形边后插入宿主正下方（NOACTIVATE）。
    /// 已就位（±1px）时跳过 SetWindowPos。返回是否就位。
    /// </summary>
    public bool PlaceInPane(int x, int y, int w, int h)
    {
        if (!CanPlace) return false;
        // 隐形边每次放置现场实测，不能吸附时缓存：它是物理像素，随子窗口当前所在显示器
        // DPI 缩放（实测 mspaint：7px@100% ↔ 9px@150%）。跨屏吸附/拖宿主跨屏后缓存值失真，
        // 可见内容缩水 2~4px，透明格透出后面的桌面形成一圈缝（且维护定时器无法自愈，
        // 因为 ±1px 跳过检查用的也是同一份失真值）
        var m = Native.GetInvisibleFrameMargins(Hwnd);
        x -= m.Left;
        y -= m.Top;
        w += m.Left + m.Right;
        h += m.Top + m.Bottom;
        if (Native.GetWindowRect(Hwnd, out var r)
            && Math.Abs(r.Left - x) <= 1 && Math.Abs(r.Top - y) <= 1
            && Math.Abs(r.Width - w) <= 1 && Math.Abs(r.Height - h) <= 1)
        {
            return true; // 已就位，避免无谓的 SetWindowPos
        }
        // 插到宿主正下方（相对插入是稳定语义）：宿主不透明部分（分隔条/边框）盖住子窗口
        // 隐形边可点击，透明格子透出子窗口。不要用 HWND_TOP——实测 Alt+Tab 切回宿主后
        // 它是静默无效调用（返回 true 但 z 序不变，子窗口被切走前的窗口一直压住）。
        // SWP_NOOWNERZORDER 必带：缺了它，移动子窗口会联动重排 owner 链——实测 VS Code
        // 的隐藏终端窗口（PseudoConsoleWindow，owner=code）被系统拖进宿主正下方槽位，
        // 与 250ms 自愈形成永久互搏 = 中线闪烁（2026-11 日志实锤）
        return Native.SetWindowPos(Hwnd, _host, x, y, w, h,
            Native.SWP_NOACTIVATE | Native.SWP_NOOWNERZORDER);
    }

    /// <summary>随宿主整体移动（dx,dy 设备像素；最小化中的子窗口不动）。</summary>
    public void MoveBy(int dx, int dy)
    {
        if (!IsAlive || Native.IsIconic(Hwnd)) return;
        if (!Native.GetWindowRect(Hwnd, out var r)) return;
        Native.SetWindowPos(Hwnd, IntPtr.Zero, r.Left + dx, r.Top + dy, 0, 0,
            Native.SWP_NOSIZE | Native.SWP_NOACTIVATE | Native.SWP_NOZORDER);
    }

    /// <summary>移出屏幕外（最小化联动；保持可见位，还原由 PlaceInPane 拉回）。</summary>
    public void MoveOffscreen()
    {
        if (!IsAlive) return;
        Native.SetWindowPos(Hwnd, IntPtr.Zero, -32000, -32000, 0, 0,
            Native.SWP_NOSIZE | Native.SWP_NOACTIVATE | Native.SWP_NOZORDER);
    }

    /// <summary>插到宿主正下方（z 序自愈；最小化中的子窗口不动）。</summary>
    public void PlaceBelowHost()
    {
        if (!IsAlive || Native.IsIconic(Hwnd)) return;
        Native.SetWindowPos(Hwnd, _host, 0, 0, 0, 0,
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE
            | Native.SWP_NOOWNERZORDER);
    }
}
