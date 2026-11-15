using System.Windows;
using System.Windows.Controls;
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
        var divider = (Border)sender;
        if (e.ClickCount >= 2)
        {
            SetRatio((int)divider.Tag, 0.5); // 双击该比例回中
            e.Handled = true;
            return;
        }
        divider.CaptureMouse();
        e.Handled = true;
    }

    private void DividerOnMouseMove(object sender, MouseEventArgs e)
    {
        var divider = (Border)sender;
        if (!divider.IsMouseCaptured) return;
        var p = e.GetPosition(_paneHost); // 内容区相对坐标（与布局几何同一原点）
        SetRatio((int)divider.Tag, Layout.RatioFromDivider((int)divider.Tag, p, ContentW, ContentH, _ratio, _ratio2, _dividerW));
        e.Handled = true;
    }

    private void DividerOnMouseUp(object sender, MouseButtonEventArgs e)
    {
        if (sender is Border { IsMouseCaptured: true } divider) divider.ReleaseMouseCapture();
        e.Handled = true;
    }

    /// <summary>写入比例（0=主 / 1=次，按当前布局钳制）并立即重摆。</summary>
    private void SetRatio(int index, double value)
    {
        double other = index == 0 ? _ratio2 : _ratio;
        double clamped = Layout.ClampRatio(index, value, other, ContentW, ContentH, _dividerW, MinPaneDip);
        if (index == 0) _ratio = clamped;
        else _ratio2 = clamped;
        UpdatePaneVisuals();
        ApplyLayout();
    }

    /// <summary>命中检测：返回命中的格子索引（null=不在任何格子内）。
    /// 判定矩形向四周外扩半条分隔条宽——分隔条带本身也算命中（归最近格，
    /// 与旧版"分隔条中心为左右分界"一致）；用 ActualWidth 直算，
    /// _content.ActualWidth 在布局回缩未完成时是旧值，会把命中算错。</summary>
    internal int? HitTestPaneAt(int deviceX, int deviceY)
    {
        if (_handle == IntPtr.Zero || !IsLoaded || WindowState == WindowState.Minimized) return null;
        var p = PointFromScreen(new Point(deviceX, deviceY));
        double bw = CurBorderW;
        // 内容区相对坐标（最大化浮层模式顶条不占布局，命中区从边框下沿开始）
        double cx = p.X - bw;
        double cy = p.Y - bw - TopInset;
        double cw = ContentW, ch = ContentH;
        if (cx < 0 || cx > cw || cy < 0 || cy > ch) return null;
        var rects = Layout.PaneRects(cw, ch, _ratio, _ratio2, _dividerW);
        double half = _dividerW / 2;
        for (int i = 0; i < rects.Length; i++)
        {
            var r = rects[i];
            if (cx >= r.X - half && cx <= r.X + r.Width + half
                && cy >= r.Y - half && cy <= r.Y + r.Height + half)
            {
                return i;
            }
        }
        return null;
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
            // 自家子窗口属于本单元（点击激活的瞬态会升到宿主上方），不算遮挡
            if (IsAttachedChild(h)) continue;
            if (!Native.IsWindowVisible(h) || Native.IsCloaked(h)) continue;
            if ((Native.GetWindowLong(h, Native.GWL_EXSTYLE) & Native.WS_EX_TRANSPARENT) != 0) continue;
            if (!Native.GetWindowRect(h, out var r)) continue;
            if (p.X >= r.Left && p.X < r.Right && p.Y >= r.Top && p.Y < r.Bottom) return true;
        }
        return false;
    }

    internal void SetDragHighlight(int? pane)
    {
        _highlight = pane;
        for (int i = 0; i < _paneGlows.Length; i++)
        {
            _paneGlows[i].Visibility = pane == i ? Visibility.Visible : Visibility.Collapsed;
        }
    }
}
