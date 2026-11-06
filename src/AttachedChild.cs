using System.Runtime.InteropServices;
using System.Windows;

namespace WindowMerger;

/// <summary>
/// 单个已吸附子窗口的吸附态。不含任何左右/几何/UI 语义，
/// 可在左右格之间整体交换（SwapSides = 引用交换）。
/// </summary>
internal sealed class AttachedChild
{
    public IntPtr Hwnd;                                // 当前子窗口
    public Native.RECT PreAttachRect;                  // 吸附前矩形（释放还原用）
    public (int L, int T, int R, int B) FrameMargins;  // 隐形边（吸附时实测）

    /// <summary>窗口仍在且存活。</summary>
    public bool IsAlive => Hwnd != IntPtr.Zero && Native.IsWindow(Hwnd);

    /// <summary>吸附时捕获吸附态：吸附前矩形（最小化中则取还原矩形）+ 隐形边实测。</summary>
    public static AttachedChild Attach(IntPtr hwnd)
    {
        var child = new AttachedChild { Hwnd = hwnd };
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

    /// <summary>纯自身操作：toolwindow 样式补挂（应用自行改回普通样式时）+ iconic/zoomed 拉回格子。</summary>
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
    }

    /// <summary>
    /// 释放还原：直角化撤销、任务栏/Alt+Tab 恢复、摘除置顶污染、回吸附前矩形。
    /// 只碰自己的 hwnd；UIPI 失败按设计静默（与旧 DetachRestore 行为一致）。
    /// </summary>
    public void Restore()
    {
        if (Hwnd == IntPtr.Zero) return;
        int pref = Native.DWMWCP_DEFAULT;
        Native.DwmSetWindowAttribute(Hwnd, Native.DWMWA_WINDOW_CORNER_PREFERENCE, ref pref, sizeof(int));
        Native.SetToolWindowStyle(Hwnd, tool: false);
        if (!Native.IsWindow(Hwnd)) return;
        var r = PreAttachRect;
        if (Native.IsIconic(Hwnd)) Native.ShowWindow(Hwnd, Native.SW_RESTORE);
        Native.SetWindowPos(Hwnd, HwndNotTopmost, 0, 0, 0, 0,
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
        Native.SetWindowPos(Hwnd, IntPtr.Zero, r.Left, r.Top, r.Width, r.Height,
            Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
    }

    private static readonly IntPtr HwndNotTopmost = new(-2);
}
