using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shell;
using System.Windows.Threading;

namespace WindowMerger;

public sealed class HostWindow : Window
{
    private const double BorderW = 2;      // 可见边框宽度
    private const double TopBarH = 28;     // 顶条高度（可拖动 + 右键菜单）
    private const double DividerW = 8;     // 中间分隔条宽度
    private const double ChromeResizeBorder = 8;
    private const double MinRatio = 0.2;
    private const double MaxRatio = 0.8;

    private const int WM_GETMINMAXINFO = 0x0024;

    private readonly AppConfig _config;
    private double _ratio;

    private Border _outer = null!;
    private Border _topBar = null!;
    private Border _divider = null!;
    private TextBlock _status = null!;
    private Border _leftGlow = null!;
    private Border _rightGlow = null!;
    private ColumnDefinition _leftCol = null!;
    private Grid _content = null!;

    private IntPtr _handle;
    private IntPtr _leftHwnd;
    private IntPtr _rightHwnd;
    private readonly Dictionary<IntPtr, Native.RECT> _preAttachRects = new();
    private readonly Dictionary<IntPtr, (int L, int T, int R, int B)> _frameMargins = new();
    private readonly Dictionary<IntPtr, int> _minimizedShowCmd = new();
    private DragAttach? _drag;
    private readonly DispatcherTimer _timer;
    private Point _lastOrigin;
    private int _highlightSlot = -1;
    private Panel _captionButtons = null!;

    private static readonly IntPtr HwndNotTopmost = new(-2);

    public HostWindow(AppConfig config)
    {
        _config = config;
        _ratio = Math.Clamp(config.Ratio, MinRatio, MaxRatio);

        Title = "窗口合并 WindowMerger";
        WindowStyle = WindowStyle.None;
        AllowsTransparency = true;
        Background = Brushes.Transparent;
        ResizeMode = ResizeMode.CanResize;
        MinWidth = 400;
        MinHeight = 300;
        Width = config.Width is double w and >= 300 ? w : 1280;
        Height = config.Height is double h and >= 300 ? h : 800;
        if (config.Left is double l && config.Top is double t && Math.Abs(l) < 20000 && Math.Abs(t) < 20000)
        {
            WindowStartupLocation = WindowStartupLocation.Manual;
            Left = l;
            Top = t;
        }
        else
        {
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
        }

        BuildUi();

        // CaptionHeight=0：顶条走 DragMove，右键才能弹自定义菜单；缩放交给 WindowChrome 的 resize 边
        WindowChrome.SetWindowChrome(this, new WindowChrome
        {
            ResizeBorderThickness = new Thickness(ChromeResizeBorder),
            CaptionHeight = 0,
            CornerRadius = new CornerRadius(0),
            GlassFrameThickness = new Thickness(0),
            UseAeroCaptionButtons = false,
        });

        LocationChanged += (_, _) => OnHostMoved();
        SizeChanged += (_, _) => { UpdatePaneWidths(); ApplyLayout(); };
        StateChanged += (_, _) => OnStateChanged();
        Activated += (_, _) =>
        {
            // 宿主激活自动升到子窗口上方，低优先级再把子窗口插回宿主下方加固相邻关系
            Dispatcher.BeginInvoke(RaiseChildrenBelow, DispatcherPriority.Background);
        };
        DpiChanged += (_, _) => ApplyLayout();
        Loaded += (_, _) => { UpdatePaneWidths(); ApplyLayout(); };
        Closing += (_, _) => OnClosingCleanup();

        _timer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(250),
        };
        _timer.Tick += (_, _) => Maintain();
    }

    // ---------- UI ----------

    private void BuildUi()
    {
        var accent = Color.FromRgb(0x0A, 0x84, 0xFF);
        var borderBrush = new SolidColorBrush(Color.FromRgb(0x3A, 0x3A, 0x3A));
        var barBrush = new SolidColorBrush(Color.FromRgb(0x20, 0x20, 0x20));
        var dividerBrush = new SolidColorBrush(Color.FromRgb(0x3C, 0x3C, 0x3C));
        var dividerHover = new SolidColorBrush(Color.FromRgb(0x2B, 0x5B, 0x8F));

        _leftGlow = MakeGlow(accent);
        _rightGlow = MakeGlow(accent);

        var leftPane = new Grid { Background = null }; // 保持透明：空格看桌面，吸附后透出子窗口
        leftPane.Children.Add(_leftGlow);
        var rightPane = new Grid { Background = null };
        rightPane.Children.Add(_rightGlow);

        _divider = new Border
        {
            Background = dividerBrush,
            Width = DividerW,
            Cursor = Cursors.SizeWE,
        };
        _divider.MouseEnter += (_, _) => _divider.Background = dividerHover;
        _divider.MouseLeave += (_, _) => _divider.Background = dividerBrush;
        _divider.MouseLeftButtonDown += DividerOnMouseDown;
        _divider.MouseMove += DividerOnMouseMove;
        _divider.MouseLeftButtonUp += DividerOnMouseUp;

        _leftCol = new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) };
        _content = new Grid { Background = null };
        _content.ColumnDefinitions.Add(_leftCol);
        _content.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(DividerW) });
        _content.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        Grid.SetColumn(leftPane, 0);
        Grid.SetColumn(_divider, 1);
        Grid.SetColumn(rightPane, 2);
        _content.Children.Add(leftPane);
        _content.Children.Add(_divider);
        _content.Children.Add(rightPane);

        _status = new TextBlock
        {
            Foreground = new SolidColorBrush(Color.FromRgb(0xD8, 0xD8, 0xD8)),
            FontSize = 12,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(10, 0, 10, 0),
            TextTrimming = TextTrimming.CharacterEllipsis,
        };

        _captionButtons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            VerticalAlignment = VerticalAlignment.Top,
            Margin = new Thickness(0, 6, 6, 0),
            Background = null,
        };
        _captionButtons.Children.Add(CaptionButton("\u2500", (_, _) => WindowState = WindowState.Minimized));
        _captionButtons.Children.Add(CaptionButton("\u25A1", (_, _) => ToggleMaximize()));
        _captionButtons.Children.Add(CaptionButton("\u2715", (_, _) => Close(), danger: true));

        var topBarGrid = new Grid();
        topBarGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        topBarGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Grid.SetColumn(_status, 0);
        Grid.SetColumn(_captionButtons, 1);
        topBarGrid.Children.Add(_status);
        topBarGrid.Children.Add(_captionButtons);

        _topBar = new Border
        {
            Background = barBrush,
            Height = TopBarH,
            Child = topBarGrid,
        };
        _topBar.MouseLeftButtonDown += TopBarOnMouseDown;

        var menu = BuildMenu();
        _topBar.ContextMenu = menu;
        _divider.ContextMenu = menu;

        var root = new DockPanel { LastChildFill = true };
        DockPanel.SetDock(_topBar, Dock.Top);
        root.Children.Add(_topBar);
        root.Children.Add(_content);

        _outer = new Border
        {
            BorderBrush = borderBrush,
            BorderThickness = new Thickness(BorderW),
            Child = root,
        };
        Content = _outer;
    }

    private ContextMenu BuildMenu()
    {
        var m = new ContextMenu();
        m.Items.Add(MakeItem("选择左窗…", (_, _) => Pick(AttachSide.Left)));
        m.Items.Add(MakeItem("选择右窗…", (_, _) => Pick(AttachSide.Right)));
        m.Items.Add(new Separator());
        m.Items.Add(MakeItem("交换左右", (_, _) => SwapSides()));
        m.Items.Add(MakeItem("全部释放（窗口回到原位）", (_, _) => ReleaseAll()));
        m.Items.Add(new Separator());
        m.Items.Add(MakeItem("退出", (_, _) => Close()));
        return m;
    }

    private static MenuItem MakeItem(string header, RoutedEventHandler onRun)
    {
        var item = new MenuItem { Header = header };
        item.Click += onRun;
        return item;
    }

    private static Button CaptionButton(string glyph, RoutedEventHandler onClick, bool danger = false)
    {
        var normal = Brushes.Transparent;
        var hover = danger
            ? new SolidColorBrush(Color.FromRgb(0xC4, 0x2B, 0x1C))
            : new SolidColorBrush(Color.FromRgb(0x3A, 0x3A, 0x3A));
        var b = new Button
        {
            Content = glyph,
            Width = 36,
            Height = 20,
            Focusable = false,
            Background = normal,
            Foreground = new SolidColorBrush(Color.FromRgb(0xD8, 0xD8, 0xD8)),
            BorderThickness = new Thickness(0),
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 11,
            Margin = new Thickness(2, 0, 0, 0),
        };
        b.MouseEnter += (_, _) => b.Background = hover;
        b.MouseLeave += (_, _) => b.Background = normal;
        b.Click += onClick;
        return b;
    }

    private void ToggleMaximize()
        => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private static Border MakeGlow(Color accent) => new()    {
        BorderBrush = new SolidColorBrush(accent),
        BorderThickness = new Thickness(3),
        CornerRadius = new CornerRadius(4),
        Margin = new Thickness(1),
        IsHitTestVisible = false,
        Visibility = Visibility.Collapsed,
    };

    // ---------- 生命周期 ----------

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        _handle = new WindowInteropHelper(this).Handle;
        HwndSource.FromHwnd(_handle)!.AddHook(WndProc);
        _lastOrigin = PointToScreen(new Point(0, 0));
        _drag = new DragAttach(this);
        _timer.Start();
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WM_GETMINMAXINFO)
        {
            // 无边框窗口最大化越过任务栏的修正：钳制到工作区
            var mmi = Marshal.PtrToStructure<MINMAXINFO>(lParam);
            IntPtr monitor = Native.MonitorFromWindow(hwnd, Native.MONITOR_DEFAULTTONEAREST);
            if (monitor != IntPtr.Zero)
            {
                var info = new Native.MONITORINFO { cbSize = Marshal.SizeOf<Native.MONITORINFO>() };
                if (Native.GetMonitorInfo(monitor, ref info))
                {
                    mmi.ptMaxPosition.X = Math.Abs(info.rcWork.Left - info.rcMonitor.Left);
                    mmi.ptMaxPosition.Y = Math.Abs(info.rcWork.Top - info.rcMonitor.Top);
                    mmi.ptMaxSize.X = Math.Abs(info.rcWork.Right - info.rcWork.Left);
                    mmi.ptMaxSize.Y = Math.Abs(info.rcWork.Bottom - info.rcWork.Top);
                }
            }
            mmi.ptMinTrackSize.X = 420;
            mmi.ptMinTrackSize.Y = 320;
            Marshal.StructureToPtr(mmi, lParam, true);
            handled = true;
        }
        return IntPtr.Zero;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MINMAXINFO
    {
        public Native.POINT ptReserved;
        public Native.POINT ptMaxSize;
        public Native.POINT ptMaxPosition;
        public Native.POINT ptMinTrackSize;
        public Native.POINT ptMaxTrackSize;
    }

    private void OnClosingCleanup()
    {
        _timer.Stop();
        _drag?.Dispose();
        _drag = null;
        ReleaseAll();

        var cfg = new AppConfig { Ratio = _ratio };
        if (WindowState == WindowState.Normal)
        {
            cfg.Left = Left;
            cfg.Top = Top;
            cfg.Width = ActualWidth;
            cfg.Height = ActualHeight;
        }
        else
        {
            var r = RestoreBounds;
            cfg.Left = r.Left;
            cfg.Top = r.Top;
            cfg.Width = r.Width;
            cfg.Height = r.Height;
        }
        ConfigStore.Save(cfg);
    }

    // ---------- 布局同步 ----------

    private void OnHostMoved()
    {
        if (_handle == IntPtr.Zero || !IsLoaded || WindowState == WindowState.Minimized) return;
        var now = PointToScreen(new Point(0, 0));
        int dx = (int)Math.Round(now.X - _lastOrigin.X);
        int dy = (int)Math.Round(now.Y - _lastOrigin.Y);
        _lastOrigin = now;
        if (dx == 0 && dy == 0) return;

        foreach (var h in new[] { _leftHwnd, _rightHwnd })
        {
            if (h == IntPtr.Zero || !Native.IsWindow(h) || Native.IsIconic(h)) continue;
            if (!Native.GetWindowRect(h, out var r)) continue;
            Native.SetWindowPos(h, IntPtr.Zero, r.Left + dx, r.Top + dy, 0, 0,
                Native.SWP_NOSIZE | Native.SWP_NOACTIVATE | Native.SWP_NOZORDER);
        }
    }

    private void ApplyLayout()
    {
        if (_handle == IntPtr.Zero || !IsLoaded) return;
        ApplyLayoutTo(_leftHwnd, 0);
        ApplyLayoutTo(_rightHwnd, 1);
    }

    private void ApplyLayoutTo(IntPtr hwnd, int slot)
    {
        if (hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) || Native.IsIconic(hwnd) || Native.IsZoomed(hwnd)) return;
        if (ActualWidth < 50 || ActualHeight < 50) return;

        var (x, y, w, h) = PaneRectDevice(slot);

        // 外扩 DWM 隐形边，可见内容才能精确填满格子
        var m = _frameMargins.TryGetValue(hwnd, out var fm) ? fm : default;
        x -= m.L;
        y -= m.T;
        w += m.L + m.R;
        h += m.T + m.B;

        if (Native.GetWindowRect(hwnd, out var r)
            && Math.Abs(r.Left - x) <= 1 && Math.Abs(r.Top - y) <= 1
            && Math.Abs(r.Width - w) <= 1 && Math.Abs(r.Height - h) <= 1)
        {
            return; // 已就位，避免无谓的 SetWindowPos
        }
        // 插到宿主正下方：可见内容与格子齐平，分隔条/边框盖在隐形边上（宿主在上可点击）
        Native.SetWindowPos(hwnd, _handle, x, y, w, h, Native.SWP_NOACTIVATE);
    }

    private (int X, int Y, int W, int H) PaneRectDevice(int slot)
    {
        double availDip = Math.Max(0, ActualWidth - 2 * BorderW - DividerW);
        double contentHDip = Math.Max(0, ActualHeight - 2 * BorderW - TopBarH);
        double leftWDip = availDip * _ratio;
        double xDip = slot == 0 ? BorderW : BorderW + leftWDip + DividerW;
        double wDip = slot == 0 ? leftWDip : availDip - leftWDip;

        var tl = PointToScreen(new Point(xDip, BorderW + TopBarH));
        var br = PointToScreen(new Point(xDip + wDip, BorderW + TopBarH + contentHDip));
        return ((int)Math.Round(tl.X), (int)Math.Round(tl.Y),
                (int)Math.Round(br.X - tl.X), (int)Math.Round(br.Y - tl.Y));
    }

    private void UpdatePaneWidths()
    {
        double avail = Math.Max(0, _content.ActualWidth - DividerW);
        _leftCol.Width = new GridLength(avail * _ratio);
    }

    private void RaiseChildrenBelow()
    {
        if (_handle == IntPtr.Zero) return;
        // 插到宿主正下方：先右后左，最终顺序（上→下）为 宿主、左、右
        foreach (var h in new[] { _rightHwnd, _leftHwnd })
        {
            if (h == IntPtr.Zero || !Native.IsWindow(h) || Native.IsIconic(h)) continue;
            Native.SetWindowPos(h, _handle, 0, 0, 0, 0,
                Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
        }
    }

    private void FixZOrder()
    {
        foreach (var h in new[] { _leftHwnd, _rightHwnd })
        {
            if (h == IntPtr.Zero || !Native.IsWindow(h) || Native.IsIconic(h)) continue;
            if (Native.GetWindow(h, Native.GW_HWNDPREV) == _handle) continue;
            RaiseChildrenBelow();
            return;
        }
    }

    private void Maintain()
    {
        bool childLost = false;
        if (_leftHwnd != IntPtr.Zero && !Native.IsWindow(_leftHwnd))
        {
            _preAttachRects.Remove(_leftHwnd);
            _frameMargins.Remove(_leftHwnd);
            _leftHwnd = IntPtr.Zero;
            childLost = true;
        }
        if (_rightHwnd != IntPtr.Zero && !Native.IsWindow(_rightHwnd))
        {
            _preAttachRects.Remove(_rightHwnd);
            _frameMargins.Remove(_rightHwnd);
            _rightHwnd = IntPtr.Zero;
            childLost = true;
        }
        UpdateStatus();
        if (childLost) UpdateHostIcon();

        if (WindowState != WindowState.Normal) return;
        bool dragging = _drag is { IsBusy: true };
        if (!dragging && _highlightSlot != -1) SetDragHighlight(-1); // 拖动事件丢失时兜底熄灭高亮
        if (dragging) return; // 有窗口正在被拖动，不对抗

        // 应用自身可能被外部改回普通样式（个别框架会重写样式），丢失时补上
        foreach (var h in new[] { _leftHwnd, _rightHwnd })
        {
            if (h == IntPtr.Zero || !Native.IsWindow(h)) continue;
            if ((Native.GetWindowLong(h, Native.GWL_EXSTYLE) & Native.WS_EX_TOOLWINDOW) == 0)
            {
                SetToolWindowStyle(h, tool: true);
            }
        }

        ApplyLayout();
        FixZOrder();
    }

    // ---------- 状态联动 ----------

    private void OnStateChanged()
    {
        switch (WindowState)
        {
            case WindowState.Minimized:
                foreach (var h in new[] { _leftHwnd, _rightHwnd })
                {
                    if (h == IntPtr.Zero || !Native.IsWindow(h)) continue;
                    var pl = new Native.WINDOWPLACEMENT { length = Marshal.SizeOf<Native.WINDOWPLACEMENT>() };
                    if (Native.GetWindowPlacement(h, ref pl)) _minimizedShowCmd[h] = pl.showCmd;
                    Native.ShowWindow(h, Native.SW_MINIMIZE);
                }
                break;

            case WindowState.Maximized:
                // 最大化只改布局：吸附窗口随格子放大，不触发系统最大化
                ApplyLayout();
                break;

            case WindowState.Normal:
                foreach (var h in new[] { _leftHwnd, _rightHwnd })
                {
                    if (h == IntPtr.Zero || !Native.IsWindow(h)) continue;
                    if (_minimizedShowCmd.TryGetValue(h, out int cmd) && cmd != Native.SW_SHOWMINIMIZED)
                    {
                        Native.ShowWindow(h, cmd == Native.SW_MAXIMIZE ? Native.SW_MAXIMIZE : Native.SW_RESTORE);
                    }
                }
                _minimizedShowCmd.Clear();
                ApplyLayout();
                break;
        }
    }

    // ---------- 吸附 ----------

    internal bool IsAttachable(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || hwnd == _handle) return false;
        if (!Native.IsWindow(hwnd) || !Native.IsWindowVisible(hwnd) || Native.IsIconic(hwnd)) return false;
        if (Native.IsCloaked(hwnd)) return false;
        if ((Native.GetWindowLong(hwnd, Native.GWL_EXSTYLE) & Native.WS_EX_TOOLWINDOW) != 0) return false;
        if (Native.GetWindow(hwnd, Native.GW_OWNER) != IntPtr.Zero) return false;
        return Native.GetPid(hwnd) != (uint)Environment.ProcessId;
    }

    internal int HitTestPaneAt(int deviceX, int deviceY)
    {
        if (_handle == IntPtr.Zero || !IsLoaded || WindowState != WindowState.Normal) return -1;
        var p = PointFromScreen(new Point(deviceX, deviceY));
        double x0 = BorderW;
        double x1 = ActualWidth - BorderW;
        double y0 = BorderW + TopBarH;
        double y1 = ActualHeight - BorderW;
        if (p.X < x0 || p.X > x1 || p.Y < y0 || p.Y > y1) return -1;
        double avail = Math.Max(1, _content.ActualWidth - DividerW);
        double split = x0 + avail * _ratio + DividerW / 2;
        return p.X < split ? 0 : 1;
    }

    internal void SetDragHighlight(int slot)
    {
        _highlightSlot = slot;
        _leftGlow.Visibility = slot == 0 ? Visibility.Visible : Visibility.Collapsed;
        _rightGlow.Visibility = slot == 1 ? Visibility.Visible : Visibility.Collapsed;
    }

    // ---------- 任务栏隐藏与图标叠加 ----------

    private static void SetToolWindowStyle(IntPtr hwnd, bool tool)
    {
        int ex = Native.GetWindowLong(hwnd, Native.GWL_EXSTYLE);
        int desired = tool ? ex | Native.WS_EX_TOOLWINDOW : ex & ~Native.WS_EX_TOOLWINDOW;
        if (desired == ex) return;
        Native.SetWindowLong(hwnd, Native.GWL_EXSTYLE, desired);
        // 任务栏按钮在显示状态翻转时才刷新
        Native.ShowWindow(hwnd, Native.SW_HIDE);
        Native.ShowWindow(hwnd, Native.SW_SHOWNA);
    }

    private BitmapSource? TryGetIconSource(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || !Native.IsWindow(hwnd)) return null;
        IntPtr hIcon = Native.SendMessage(hwnd, Native.WM_GETICON, (IntPtr)Native.ICON_BIG, IntPtr.Zero);
        if (hIcon == IntPtr.Zero)
            hIcon = (IntPtr)Native.GetClassLong(hwnd, Native.GCLP_HICON);
        if (hIcon == IntPtr.Zero)
            hIcon = Native.SendMessage(hwnd, Native.WM_GETICON, (IntPtr)Native.ICON_SMALL2, IntPtr.Zero);
        if (hIcon == IntPtr.Zero)
            hIcon = (IntPtr)Native.GetClassLong(hwnd, Native.GCLP_HICONSM);
        if (hIcon == IntPtr.Zero) return null;

        var src = Imaging.CreateBitmapSourceFromHIcon(hIcon, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
        Native.DestroyIcon(hIcon);
        src.Freeze();
        return src;
    }

    private void UpdateHostIcon()
    {
        var l = TryGetIconSource(_leftHwnd);
        var r = TryGetIconSource(_rightHwnd);
        if (l == null && r == null)
        {
            Icon = null;
            return;
        }
        if (l == null)
        {
            Icon = r;
            return;
        }
        if (r == null)
        {
            Icon = l;
            return;
        }

        // 两枚图标错位叠放
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            dc.DrawImage(l, new Rect(0, 0, 24, 24));
            dc.DrawImage(r, new Rect(8, 8, 24, 24));
        }
        var rtb = new RenderTargetBitmap(32, 32, 96, 96, PixelFormats.Pbgra32);
        rtb.Render(visual);
        rtb.Freeze();
        Icon = rtb;
    }

    internal void TryAttach(AttachSide side, IntPtr hwnd)
    {
        if (!IsAttachable(hwnd)) return;
        int slot = side == AttachSide.Left ? 0 : 1;
        IntPtr cur = slot == 0 ? _leftHwnd : _rightHwnd;
        IntPtr other = slot == 0 ? _rightHwnd : _leftHwnd;

        if (hwnd == cur)
        {
            ApplyLayoutTo(hwnd, slot); // 拖走又拖回来：吸附回原格
            return;
        }
        if (hwnd == other)
        {
            // 拖到另一侧 = 换到另一侧
            if (slot == 0) { _rightHwnd = IntPtr.Zero; _leftHwnd = hwnd; }
            else { _leftHwnd = IntPtr.Zero; _rightHwnd = hwnd; }
            ApplyLayoutTo(hwnd, slot);
            UpdateStatus();
            return;
        }

        if (cur != IntPtr.Zero) DetachRestore(cur); // 替换：原窗口回到吸附前位置
        if (slot == 0) _leftHwnd = hwnd; else _rightHwnd = hwnd;
        SavePreAttachRect(hwnd);
        _frameMargins[hwnd] = Native.GetInvisibleFrameMargins(hwnd);
        if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
        SetToolWindowStyle(hwnd, tool: true);
        ApplyLayoutTo(hwnd, slot);
        RaiseChildrenBelow();
        UpdateStatus();
        UpdateHostIcon();
    }

    private void SavePreAttachRect(IntPtr hwnd)
    {
        if (Native.IsIconic(hwnd))
        {
            var pl = new Native.WINDOWPLACEMENT { length = Marshal.SizeOf<Native.WINDOWPLACEMENT>() };
            if (Native.GetWindowPlacement(hwnd, ref pl))
            {
                _preAttachRects[hwnd] = pl.rcNormalPosition;
                return;
            }
        }
        if (Native.GetWindowRect(hwnd, out var r)) _preAttachRects[hwnd] = r;
    }

    private void DetachRestore(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return;
        _frameMargins.Remove(hwnd);
        SetToolWindowStyle(hwnd, tool: false); // 任务栏/Alt+Tab 恢复
        if (!_preAttachRects.Remove(hwnd, out var r)) return;
        if (!Native.IsWindow(hwnd)) return;
        if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
        // 摘除可能被外部污染的置顶标记，窗口回到普通层
        Native.SetWindowPos(hwnd, HwndNotTopmost, 0, 0, 0, 0,
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
        Native.SetWindowPos(hwnd, IntPtr.Zero, r.Left, r.Top, r.Width, r.Height,
            Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
    }

    private void ReleaseAll()
    {
        DetachRestore(_leftHwnd);
        DetachRestore(_rightHwnd);
        _leftHwnd = IntPtr.Zero;
        _rightHwnd = IntPtr.Zero;
        _minimizedShowCmd.Clear();
        UpdateStatus();
        UpdateHostIcon();
    }

    private void SwapSides()
    {
        (_leftHwnd, _rightHwnd) = (_rightHwnd, _leftHwnd);
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

    // ---------- 交互 ----------

    private void TopBarOnMouseDown(object sender, MouseButtonEventArgs e)
    {
        // 按钮区域的按下交给按钮，不触发拖动/双击最大化
        if (e.OriginalSource is DependencyObject src && _captionButtons.IsAncestorOf(src)) return;
        if (e.ClickCount >= 2)
        {
            WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
            e.Handled = true;
            return;
        }
        if (WindowState == WindowState.Maximized) return;
        try
        {
            DragMove();
        }
        catch (InvalidOperationException)
        {
            // 鼠标已释放的竞态，忽略
        }
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
        double avail = Math.Max(1, _content.ActualWidth - DividerW);
        _ratio = Math.Clamp(p.X / avail, MinRatio, MaxRatio);
        UpdatePaneWidths();
        ApplyLayout();
        e.Handled = true;
    }

    private void DividerOnMouseUp(object sender, MouseButtonEventArgs e)
    {
        if (_divider.IsMouseCaptured) _divider.ReleaseMouseCapture();
        e.Handled = true;
    }

    // ---------- 状态栏 ----------

    private void UpdateStatus()
    {
        if (_status is null) return;
        if (_leftHwnd == IntPtr.Zero && _rightHwnd == IntPtr.Zero)
        {
            _status.Text = "把任意窗口拖进来吸附，或右键打开菜单选择左/右窗";
            return;
        }
        _status.Text = $"左: {PaneTitle(_leftHwnd)}    右: {PaneTitle(_rightHwnd)}";
    }

    private static string PaneTitle(IntPtr hwnd)
        => hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) ? "空" : Truncate(Native.GetTitle(hwnd), 40);

    private static string Truncate(string s, int max)
        => s.Length <= max ? s : s[..(max - 1)] + "…";
}
