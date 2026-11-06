using System.Windows;
using System.Windows.Input;

namespace WindowMerger;

// ---------- 拖拽交互（顶条拖动/最大化拖动还原/分隔条拖动） ----------

public sealed partial class HostWindow : Window
{
    private double _maxDragOffX, _maxDragOffY; // 拖动锚点：光标相对还原窗口左上角的设备像素偏移（按整窗比例）
    private bool _maxDragArmed;     // 已按下、未超过拖动阈值
    private bool _maxDragActive;    // 已还原，手动拖动进行中
    private Point _maxDragGrabPoint;

    private void TopBarOnMouseDown(object sender, MouseButtonEventArgs e)
    {
        // 按钮区域的按下交给按钮，不触发拖动/双击最大化
        if (e.OriginalSource is DependencyObject src && _captionButtons.IsAncestorOf(src)) return;
        if (e.ClickCount >= 2)
        {
            ToggleMaximize();
            e.Handled = true;
            return;
        }
        if (WindowState == WindowState.Maximized)
        {
            // 按下不还原（原地点击应保持最大化）：捕获鼠标，拖动超过系统阈值才还原继续拖
            _maxDragGrabPoint = e.GetPosition(this);
            _maxDragArmed = true;
            _topBar.CaptureMouse();
            e.Handled = true;
            return;
        }
        try
        {
            DragMove();
        }
        catch (InvalidOperationException)
        {
            // 鼠标已释放的竞态，忽略
        }
    }

    private void TopBarOnMouseMove(object sender, MouseEventArgs e)
    {
        if (!_topBar.IsMouseCaptured || e.LeftButton != MouseButtonState.Pressed) return;
        var p = e.GetPosition(this);
        if (_maxDragArmed)
        {
            if (Math.Abs(p.X - _maxDragGrabPoint.X) < SystemParameters.MinimumHorizontalDragDistance
                && Math.Abs(p.Y - _maxDragGrabPoint.Y) < SystemParameters.MinimumVerticalDragDistance) return;
            _maxDragArmed = false;
            StartMaxRestoreDrag(p);
            return;
        }
        if (!_maxDragActive) return;
        // 手动拖动：光标钉在还原窗口的同一比例位置（与还原定位同一锚点，无跳变）。
        // 不用 DragMove：其模态循环与还原/捕获状态变化有竞态，实测位移会被重复应用
        var curDev = PointToScreen(p);
        int nx = (int)Math.Round(curDev.X - _maxDragOffX);
        int ny = (int)Math.Round(curDev.Y - _maxDragOffY);
        Native.SetWindowPos(_handle, IntPtr.Zero, nx, ny, 0, 0,
            Native.SWP_NOSIZE | Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
    }

    private void TopBarOnMouseUp(object sender, MouseButtonEventArgs e)
    {
        if (_topBar.IsMouseCaptured) _topBar.ReleaseMouseCapture();
        _maxDragArmed = false;
        _maxDragActive = false;
    }

    /// <summary>
    /// 最大化拖动开始：按"鼠标在整窗中的占比"还原定位——光标在最大化窗口的
    /// 相对位置 (grabX/宽, grabY/高)，还原后仍钉在同一相对位置，之后 MouseMove
    /// 以同一锚点跟随直到松开。还原矩形提前取自 RestoreBounds：StateChanged 早于
    /// 尺寸回缩完成，不能读还原后的 ActualWidth。
    /// </summary>
    private void StartMaxRestoreDrag(Point grabDip)
    {
        var cursorDev = PointToScreen(grabDip);
        var m = PresentationSource.FromVisual(this)?.CompositionTarget?.TransformToDevice;
        double scaleX = m?.M11 ?? 1, scaleY = m?.M22 ?? 1;
        double ratioX = Math.Clamp(grabDip.X / ActualWidth, 0, 1);
        double ratioY = Math.Clamp(grabDip.Y / ActualHeight, 0, 1);
        var rb = RestoreBounds;

        WindowState = WindowState.Normal;
        _maxDragOffX = ratioX * rb.Width * scaleX;
        _maxDragOffY = ratioY * rb.Height * scaleY;
        int nx = (int)Math.Round(cursorDev.X - _maxDragOffX);
        int ny = (int)Math.Round(cursorDev.Y - _maxDragOffY);
        Native.SetWindowPos(_handle, IntPtr.Zero, nx, ny, 0, 0,
            Native.SWP_NOSIZE | Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
        _maxDragActive = true;
        if (!_topBar.IsMouseCaptured) _topBar.CaptureMouse(); // 状态变化可能丢捕获，重新拿住以继续收 MouseMove
    }

    private void DividerOnMouseDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ClickCount >= 2)
        {
            _ratio = 0.5;
            UpdatePaneWidths();
            ApplyLayout();
            e.Handled = true;
            return;
        }
        _divider.CaptureMouse();
        e.Handled = true;
    }

    private void DividerOnMouseMove(object sender, MouseEventArgs e)
    {
        if (!_divider.IsMouseCaptured) return;
        var p = e.GetPosition(_content);
        double avail = Math.Max(1, ActualWidth - 2 * CurBorderW - _dividerW);
        _ratio = Math.Clamp((p.X + 2 * CurBorderW) / avail, MinRatio, MaxRatio);
        UpdatePaneWidths();
        ApplyLayout();
        e.Handled = true;
    }

    private void DividerOnMouseUp(object sender, MouseButtonEventArgs e)
    {
        if (_divider.IsMouseCaptured) _divider.ReleaseMouseCapture();
        e.Handled = true;
    }

    /// <summary>命中检测：返回命中的槽位（null=不在任何格子内）。</summary>
    internal AttachSide? HitTestPaneAt(int deviceX, int deviceY)
    {
        if (_handle == IntPtr.Zero || !IsLoaded || WindowState == WindowState.Minimized) return null;
        var p = PointFromScreen(new Point(deviceX, deviceY));
        double bw = CurBorderW;
        double x0 = bw;
        double x1 = ActualWidth - bw;
        double y0 = bw + _topBarH;
        double y1 = ActualHeight - bw;
        if (p.X < x0 || p.X > x1 || p.Y < y0 || p.Y > y1) return null;
        // 与 PaneRectDevice/UpdatePaneWidths 同一公式（ActualWidth 直算）：
        // _content.ActualWidth 在布局回缩未完成时是旧值，会把命中分界算错
        double avail = Math.Max(1, ActualWidth - 2 * bw - _dividerW);
        double split = x0 + avail * _ratio + _dividerW / 2;
        return p.X < split ? AttachSide.Left : AttachSide.Right;
    }

    /// <summary>
    /// 光标处宿主是否被其他窗口压住（拖入吸附/亮框的前置判定）：从 z 序顶端向下遍历到宿主
    /// 为止，跳过被拖窗口本身（拖动中它必然悬在光标下且临时升到顶层），途中任何可见窗口按
    /// 矩形命中光标点即视为遮挡——用户看到的不是我们的格子。WS_EX_TRANSPARENT 的点击穿透
    /// 层不算遮挡。不能用 WindowFromPoint 直判"最顶层是否宿主"：格子区域 alpha=0 在 OS 层
    /// 点击穿透，会拿到宿主后面的窗口，把拖入空格子（吸附主入口）误判成遮挡。
    /// </summary>
    internal bool IsCoveredAtCursor(IntPtr draggedHwnd)
    {
        if (_handle == IntPtr.Zero || !IsLoaded) return false;
        if (!Native.GetCursorPos(out var p)) return false;
        for (IntPtr h = Native.GetTopWindow(IntPtr.Zero); h != IntPtr.Zero && h != _handle;
             h = Native.GetWindow(h, Native.GW_HWNDNEXT))
        {
            if (h == draggedHwnd) continue;
            if (!Native.IsWindowVisible(h) || Native.IsCloaked(h)) continue;
            if ((Native.GetWindowLong(h, Native.GWL_EXSTYLE) & Native.WS_EX_TRANSPARENT) != 0) continue;
            if (!Native.GetWindowRect(h, out var r)) continue;
            if (p.X >= r.Left && p.X < r.Right && p.Y >= r.Top && p.Y < r.Bottom) return true;
        }
        return false;
    }

    internal void SetDragHighlight(AttachSide? side)
    {
        _highlight = side;
        _leftGlow.Visibility = side == AttachSide.Left ? Visibility.Visible : Visibility.Collapsed;
        _rightGlow.Visibility = side == AttachSide.Right ? Visibility.Visible : Visibility.Collapsed;
    }
}
