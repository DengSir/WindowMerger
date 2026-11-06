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
    public Native.RECT PreAttachRect;                  // 吸附前矩形（释放还原用）
    public (int L, int T, int R, int B) FrameMargins;  // 隐形边（吸附时实测）

    private static readonly IntPtr HwndNotTopmost = new(-2);

    private AttachedChild(IntPtr host, IntPtr hwnd)
    {
        _host = host;
        Hwnd = hwnd;
    }

    /// <summary>吸附时捕获吸附态：吸附前矩形（最小化中则取还原矩形）+ 隐形边实测。</summary>
    public static AttachedChild Attach(IntPtr host, IntPtr hwnd)
    {
        var child = new AttachedChild(host, hwnd);
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
        child.FrameMargins = Native.GetInvisibleFrameMargins(hwnd);
        return child;
    }

    /// <summary>窗口仍在且存活。</summary>
    public bool IsAlive => Hwnd != IntPtr.Zero && Native.IsWindow(Hwnd);

    /// <summary>存活且处于可放置状态（非最小化/非最大化）。</summary>
    public bool CanPlace => IsAlive && !Native.IsIconic(Hwnd) && !Native.IsZoomed(Hwnd);

    /// <summary>吸附前置：直角化 + iconic 还原 + toolwindow 样式。</summary>
    public void PrepareForDock()
    {
        Native.SetSquareCorners(Hwnd, square: true);
        if (Native.IsIconic(Hwnd)) Native.ShowWindow(Hwnd, Native.SW_RESTORE);
        Native.SetToolWindowStyle(Hwnd, tool: true);
    }

    /// <summary>解除吸附外观：圆角还原 + 摘 toolwindow（不动几何）。</summary>
    public void Undock()
    {
        Native.SetSquareCorners(Hwnd, square: false);
        Native.SetToolWindowStyle(Hwnd, tool: false);
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
        Native.SetWindowPos(Hwnd, HwndNotTopmost, 0, 0, 0, 0,
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
        Native.SetWindowPos(Hwnd, IntPtr.Zero, r.Left, r.Top, r.Width, r.Height,
            Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
    }

    /// <summary>确保处于吸附位的正常可见状态：toolwindow 样式、非最小化/最大化、可见。</summary>
    public void EnsureDockedState()
    {
        if (!IsAlive) return;
        if ((Native.GetWindowLong(Hwnd, Native.GWL_EXSTYLE) & Native.WS_EX_TOOLWINDOW) == 0)
        {
            Native.SetToolWindowStyle(Hwnd, tool: true);
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
        // 外扩自身隐形边，可见内容才能精确填满格子
        x -= FrameMargins.L;
        y -= FrameMargins.T;
        w += FrameMargins.L + FrameMargins.R;
        h += FrameMargins.T + FrameMargins.B;
        if (Native.GetWindowRect(Hwnd, out var r)
            && Math.Abs(r.Left - x) <= 1 && Math.Abs(r.Top - y) <= 1
            && Math.Abs(r.Width - w) <= 1 && Math.Abs(r.Height - h) <= 1)
        {
            return true; // 已就位，避免无谓的 SetWindowPos
        }
        // 插到宿主正下方（相对插入是稳定语义）：宿主不透明部分（分隔条/边框）盖住子窗口
        // 隐形边可点击，透明格子透出子窗口。不要用 HWND_TOP——实测 Alt+Tab 切回宿主后
        // 它是静默无效调用（返回 true 但 z 序不变，子窗口被切走前的窗口一直压住）
        return Native.SetWindowPos(Hwnd, _host, x, y, w, h, Native.SWP_NOACTIVATE);
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
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
    }
}
