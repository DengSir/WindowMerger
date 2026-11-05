using System.IO;
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
    private const double BorderW = 2;      // 可见边框宽度（最大化时隐藏为 0）
    private const double TopBarH = 28;     // 顶条高度
    private const double DividerW = 8;     // 中间分隔条宽度
    private const double ChromeResizeBorder = 8;
    private const double MinRatio = 0.2;
    private const double MaxRatio = 0.8;

    private const int WM_GETMINMAXINFO = 0x0024;
    private const int WM_SETTINGCHANGE = 0x001A;

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
    private DragAttach? _drag;
    private readonly DispatcherTimer _timer;
    private Point _lastOrigin;
    private int _highlightSlot = -1;
    private Panel _captionButtons = null!;
    private Button _maxButton = null!;
    private Button _pickLeftButton = null!;
    private Button _pickRightButton = null!;
    private string? _notice;
    private DateTime _noticeUntil;
    private readonly string? _cliLeft;
    private readonly string? _cliRight;
    private bool _cliTargetsDone;
    private Button _themeButton = null!;
    private Border _leftPaneBorder = null!;
    private Border _rightPaneBorder = null!;
    private readonly List<(Button Button, bool Danger)> _captionButtonList = new();
    private Image _leftThumb = null!;
    private Image _rightThumb = null!;
    private BitmapSource? _capLeft;
    private BitmapSource? _capRight;

    private static readonly IntPtr HwndNotTopmost = new(-2);

    /// <summary>当前生效的边框宽度：最大化时边框隐藏，格子铺满窗口。</summary>
    private double CurBorderW => WindowState == WindowState.Maximized ? 0 : BorderW;

    public HostWindow(AppConfig config, string? cliLeft = null, string? cliRight = null)
    {
        _cliLeft = string.IsNullOrWhiteSpace(cliLeft) ? null : cliLeft;
        _cliRight = string.IsNullOrWhiteSpace(cliRight) ? null : cliRight;
        if (Enum.TryParse<AppThemeMode>(config.Theme, true, out var mode)) AppTheme.Mode = mode;
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
            ShowAttachedChildren();
            // 宿主激活升到子窗口上方后，低优先级把子窗口插回宿主正下方加固相邻关系
            Dispatcher.BeginInvoke(RaiseChildrenBelow, DispatcherPriority.Background);
        };
        DpiChanged += (_, _) => ApplyLayout();
        Loaded += (_, _) => { UpdatePaneWidths(); ApplyLayout(); AttachStartupTargets(); };
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

        _leftGlow = MakeGlow(accent);
        _rightGlow = MakeGlow(accent);

        // 格子四周 2px 框线（与外边框同色）：子窗口可见边缘与格子齐平，
        // 外扩/取整带来的最后一像素缝透出的是框线色而非桌面壁纸；内部保持透明。
        // 缩略图 Image 放在格子底层：DWM 实时预览截取宿主表面时会带上子窗口画面，
        // 任务栏悬停预览因此能看到两个吸附窗口（真子窗口浮在宿主上方遮住实图）
        _leftThumb = new Image { Stretch = Stretch.Fill, IsHitTestVisible = false };
        _rightThumb = new Image { Stretch = Stretch.Fill, IsHitTestVisible = false };
        var leftInner = new Grid { Background = null };
        leftInner.Children.Add(_leftThumb);
        leftInner.Children.Add(_leftGlow);
        var rightInner = new Grid { Background = null };
        rightInner.Children.Add(_rightThumb);
        rightInner.Children.Add(_rightGlow);
        _leftPaneBorder = new Border { Background = null, BorderBrush = AppTheme.Brush(AppTheme.Current().Border), BorderThickness = new Thickness(2), Child = leftInner };
        _rightPaneBorder = new Border { Background = null, BorderBrush = AppTheme.Brush(AppTheme.Current().Border), BorderThickness = new Thickness(2), Child = rightInner };

        _divider = new Border
        {
            Background = AppTheme.Brush(AppTheme.Current().Divider),
            Width = DividerW,
            Cursor = Cursors.SizeWE,
        };
        _divider.MouseEnter += (_, _) => _divider.Background = AppTheme.Brush(AppTheme.Current().DividerHover);
        _divider.MouseLeave += (_, _) => _divider.Background = AppTheme.Brush(AppTheme.Current().Divider);
        _divider.MouseLeftButtonDown += DividerOnMouseDown;
        _divider.MouseMove += DividerOnMouseMove;
        _divider.MouseLeftButtonUp += DividerOnMouseUp;

        if (Icons.Grip is string gripGlyph && Icons.Family is not null)
        {
            _divider.Child = new TextBlock
            {
                Text = gripGlyph,
                FontFamily = Icons.Family,
                FontSize = 9,
                Foreground = new SolidColorBrush(Color.FromArgb(0x70, 0xFF, 0xFF, 0xFF)),
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
                IsHitTestVisible = false,
            };
        }

        _leftCol = new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) };
        _content = new Grid { Background = null };
        _content.ColumnDefinitions.Add(_leftCol);
        _content.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(DividerW) });
        _content.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        Grid.SetColumn(_leftPaneBorder, 0);
        Grid.SetColumn(_divider, 1);
        Grid.SetColumn(_rightPaneBorder, 2);
        _content.Children.Add(_leftPaneBorder);
        _content.Children.Add(_divider);
        _content.Children.Add(_rightPaneBorder);

        _status = new TextBlock
        {
            Foreground = AppTheme.Brush(AppTheme.Current().Text),
            FontSize = 12,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(10, 0, 10, 0),
            TextTrimming = TextTrimming.CharacterEllipsis,
        };

        _captionButtons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            VerticalAlignment = VerticalAlignment.Stretch, // 按钮占满顶条整行
            Margin = new Thickness(0),                     // 顶到最右边
            Background = null,
        };
        // 顶条功能组：[左][右][交换][释放][主题] | [─][□][✕]
        // 左/右按钮状态翻转：空格时吸附选择，有吸附窗口时变为释放该侧
        _pickLeftButton = CaptionButton(Icons.PickLeft!, (_, _) =>
        {
            if (_leftHwnd == IntPtr.Zero) Pick(AttachSide.Left);
            else ReleaseSide(0);
        }, width: 30, tooltip: "选择左窗…");
        _captionButtons.Children.Add(_pickLeftButton);
        _pickRightButton = CaptionButton(Icons.PickRight!, (_, _) =>
        {
            if (_rightHwnd == IntPtr.Zero) Pick(AttachSide.Right);
            else ReleaseSide(1);
        }, width: 30, tooltip: "选择右窗…");
        _captionButtons.Children.Add(_pickRightButton);
        _captionButtons.Children.Add(CaptionButton(Icons.Swap!, (_, _) => SwapSides(), width: 30, tooltip: "交换左右"));
        _captionButtons.Children.Add(CaptionButton(Icons.Release!, (_, _) => ReleaseAll(), width: 30, tooltip: "全部释放（窗口回到原位）"));
        _themeButton = CaptionButton(ThemeGlyph(), (_, _) => CycleTheme(), width: 30, tooltip: ThemeTooltip());
        _captionButtons.Children.Add(_themeButton);
        _captionButtons.Children.Add(CaptionSeparator());
        _captionButtons.Children.Add(CaptionButton(Icons.Minimize, (_, _) => WindowState = WindowState.Minimized, tooltip: "最小化"));
        _maxButton = CaptionButton(Icons.Maximize, (_, _) => ToggleMaximize(), font: Icons.MaximizeFont, tooltip: "最大化");
        _captionButtons.Children.Add(_maxButton);
        _captionButtons.Children.Add(CaptionButton(Icons.Close, (_, _) => Close(), danger: true, fontSize: 16, tooltip: "关闭"));
        UpdateMaxGlyph(); // 初始字体/内容配对：f096 空心方块必须配 Regular 字体（solid 里有同码位实心别名）

        var topBarGrid = new Grid();
        topBarGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        topBarGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Grid.SetColumn(_status, 0);
        Grid.SetColumn(_captionButtons, 1);
        topBarGrid.Children.Add(_status);
        topBarGrid.Children.Add(_captionButtons);

        _topBar = new Border
        {
            Background = AppTheme.Brush(AppTheme.Current().Bar),
            Height = TopBarH,
            Child = topBarGrid,
        };
        _topBar.MouseLeftButtonDown += TopBarOnMouseDown;

        var root = new DockPanel { LastChildFill = true };
        DockPanel.SetDock(_topBar, Dock.Top);
        root.Children.Add(_topBar);
        root.Children.Add(_content);

        _outer = new Border
        {
            BorderBrush = AppTheme.Brush(AppTheme.Current().Border),
            BorderThickness = new Thickness(BorderW),
            Child = root,
        };
        Content = _outer;
    }

    // ---------- 主题 ----------

    private string ThemeGlyph() => AppTheme.Mode switch
    {
        AppThemeMode.Dark => "\uF186",   // moon
        AppThemeMode.Light => "\uF185",  // sun
        _ => "\uF042",                   // circle-half-stroke（跟随系统）
    };

    private string ThemeTooltip()
    {
        string state = AppTheme.Mode switch
        {
            AppThemeMode.Dark => "深色",
            AppThemeMode.Light => "浅色",
            _ => AppTheme.IsDarkNow ? "跟随系统（当前深色）" : "跟随系统（当前浅色）",
        };
        return $"主题：{state}，点击切换";
    }

    private void CycleTheme()
    {
        AppTheme.Mode = AppTheme.Mode switch
        {
            AppThemeMode.Auto => AppThemeMode.Dark,
            AppThemeMode.Dark => AppThemeMode.Light,
            _ => AppThemeMode.Auto,
        };
        ApplyTheme();
        SaveConfig();
    }

    private void ApplyTheme()
    {
        var p = AppTheme.Current();
        _outer.BorderBrush = AppTheme.Brush(p.Border);
        _leftPaneBorder.BorderBrush = AppTheme.Brush(p.Border);
        _rightPaneBorder.BorderBrush = AppTheme.Brush(p.Border);
        _topBar.Background = AppTheme.Brush(p.Bar);
        _status.Foreground = AppTheme.Brush(p.Text);
        _divider.Background = AppTheme.Brush(p.Divider);
        foreach (var (b, _) in _captionButtonList) b.Foreground = AppTheme.Brush(p.Text);
        if (_themeButton is not null)
        {
            _themeButton.Content = ThemeGlyph();
            _themeButton.ToolTip = ThemeTooltip();
        }
    }

    private void SaveConfig()
    {
        var cfg = new AppConfig { Ratio = _ratio, Theme = AppTheme.Mode.ToString() };
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

    private static Border CaptionSeparator() => new()
    {
        Width = 1,
        Margin = new Thickness(4, 6, 4, 6),
        Background = new SolidColorBrush(Color.FromRgb(0x4A, 0x4A, 0x4A)),
        VerticalAlignment = VerticalAlignment.Stretch,
    };

    private Button CaptionButton(string glyph, RoutedEventHandler onClick, bool danger = false,
        double fontSize = 13, double width = 36, string? tooltip = null, FontFamily? font = null)
    {
        // 默认 WPF 按钮模板会在 IsMouseOver 时覆盖亮蓝色 chrome，这里用极简模板只呈现 Background；
        // 悬停色在事件时从当前主题取，切主题无需重建按钮
        var template = new ControlTemplate(typeof(Button));
        var border = new FrameworkElementFactory(typeof(Border));
        border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Button.BackgroundProperty));
        var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
        presenter.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center);
        presenter.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
        border.AppendChild(presenter);
        template.VisualTree = border;

        var b = new Button
        {
            Content = glyph,
            Width = width,
            Focusable = false,
            Background = Brushes.Transparent,
            Foreground = AppTheme.Brush(AppTheme.Current().Text),
            BorderThickness = new Thickness(0),
            FontFamily = font ?? Icons.Family ?? new FontFamily("Segoe UI"),
            FontSize = Icons.Family != null || font != null ? fontSize : 11,
            Margin = new Thickness(2, 0, 0, 0),
            ToolTip = tooltip,
            Template = template,
        };
        b.MouseEnter += (_, _) => b.Background = AppTheme.Brush(
            danger ? AppTheme.Current().DangerHover : AppTheme.Current().ButtonHover);
        b.MouseLeave += (_, _) => b.Background = Brushes.Transparent;
        b.Click += onClick;
        _captionButtonList.Add((b, danger));
        return b;
    }

    private void UpdateMaxGlyph()
    {
        if (_maxButton is null) return;
        if (WindowState == WindowState.Maximized)
        {
            _maxButton.Content = Icons.Restore;
            _maxButton.FontFamily = Icons.RestoreFont ?? _maxButton.FontFamily;
        }
        else
        {
            _maxButton.Content = Icons.Maximize;
            _maxButton.FontFamily = Icons.MaximizeFont ?? _maxButton.FontFamily;
        }
    }

    private void ToggleMaximize()
        => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private static Border MakeGlow(Color accent) => new()
    {
        BorderBrush = new SolidColorBrush(accent),
        BorderThickness = new Thickness(5),
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
        else if (msg == WM_SETTINGCHANGE)
        {
            // Windows 主题切换（深浅色）：Auto 模式下实时跟随
            if (AppTheme.Mode == AppThemeMode.Auto && Marshal.PtrToStringAuto(lParam) == "ImmersiveColorSet")
            {
                Dispatcher.BeginInvoke(ApplyTheme, DispatcherPriority.Background);
            }
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
        SaveConfig();
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

    private bool ApplyLayoutTo(IntPtr hwnd, int slot)
    {
        if (hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) || Native.IsIconic(hwnd) || Native.IsZoomed(hwnd)) return false;
        if (ActualWidth < 50 || ActualHeight < 50) return false;

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
            return true; // 已就位，避免无谓的 SetWindowPos
        }
        // 插到宿主正下方：可见内容与格子齐平，分隔条/边框盖在隐形边上（宿主在上可点击）
        return Native.SetWindowPos(hwnd, _handle, x, y, w, h, Native.SWP_NOACTIVATE);
    }

    private (int X, int Y, int W, int H) PaneRectDevice(int slot)
    {
        double bw = CurBorderW;
        double availDip = Math.Max(0, ActualWidth - 2 * bw - DividerW);
        double contentHDip = Math.Max(0, ActualHeight - 2 * bw - TopBarH);
        double leftWDip = availDip * _ratio;
        double xDip = slot == 0 ? bw : bw + leftWDip + DividerW;
        double wDip = slot == 0 ? leftWDip : availDip - leftWDip;

        var tl = PointToScreen(new Point(xDip, bw + TopBarH));
        var br = PointToScreen(new Point(xDip + wDip, bw + TopBarH + contentHDip));
        return ((int)Math.Round(tl.X), (int)Math.Round(tl.Y),
                (int)Math.Round(br.X - tl.X), (int)Math.Round(br.Y - tl.Y));
    }

    private void UpdatePaneWidths()
    {
        // 用窗口 ActualWidth 直算（与 PaneRectDevice 同一公式），不能用 _content.ActualWidth——
        // 最大化还原时 StateChanged 早于尺寸回缩完成，读到的旧值会把分隔条顶到错误位置
        double avail = Math.Max(0, ActualWidth - 2 * CurBorderW - DividerW);
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

        if (WindowState == WindowState.Minimized) return; // 最小化时不布局；最大化也要自愈
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

        // 吸附子窗口没有任务栏按钮，最小化后无从手动还原；独立最大化则摧毁合并布局——
        // 宿主可见期间两种状态一律拉回格子自愈（子窗口自身没有"最大化"概念）
        foreach (var h in new[] { _leftHwnd, _rightHwnd })
        {
            if (h == IntPtr.Zero || !Native.IsWindow(h)) continue;
            if (Native.IsIconic(h) || Native.IsZoomed(h)) Native.ShowWindow(h, Native.SW_RESTORE);
        }

        RefreshChildCaptures(); // 缓存子窗口截图供任务栏合成预览使用

        UpdatePaneWidths(); // 分隔条视觉位置与 _ratio 的持续对账（自愈任何布局漂移）
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
                    Native.ShowWindow(h, Native.SW_MINIMIZE);
                }
                break;

            case WindowState.Maximized:
            case WindowState.Normal:
                // 最大化只改布局：吸附窗口随格子放大，不触发系统最大化；边框同步隐藏/恢复。
                // 立即按当前窗口宽校一次；WPF 尺寸回缩/边框变化完成后再校一次（Loaded 优先级），
                // 消除事件时序导致的分隔条位置漂移
                ShowAttachedChildren();
                if (_outer is not null) _outer.BorderThickness = new Thickness(CurBorderW);
                UpdatePaneWidths();
                ApplyLayout();
                Dispatcher.BeginInvoke(() => { UpdatePaneWidths(); ApplyLayout(); }, DispatcherPriority.Loaded);
                break;
        }

        UpdateMaxGlyph();
    }

    /// <summary>
    /// 宿主回到可见状态时把所有非正常态（最小化/独立最大化）的子窗口拉回格子。
    /// 子窗口是 tool window 没有任务栏按钮，不在这里还原就永远回不来；
    /// 最大化路径尤其必要：从最大化最小化后点任务栏还原直接进 Maximized，不经过 Normal。
    /// </summary>
    private void ShowAttachedChildren()
    {
        foreach (var h in new[] { _leftHwnd, _rightHwnd })
        {
            if (h == IntPtr.Zero || !Native.IsWindow(h)) continue;
            if (Native.IsIconic(h) || Native.IsZoomed(h)) Native.ShowWindow(h, Native.SW_RESTORE);
        }
    }

    // ---------- 吸附 ----------

    /// <summary>
    /// 命令行吸附：WindowMerger.exe [左进程名] [右进程名]，Loaded 后执行一次。
    /// 进程名可带可不带 .exe（大小写不敏感）；同名多窗口取面积最大的；
    /// 未找到的跳过并在状态栏提示；已吸附的 hwnd 去重。
    /// </summary>
    private void AttachStartupTargets()
    {
        if (_cliTargetsDone || _cliLeft is null && _cliRight is null) return;
        _cliTargetsDone = true;

        var targets = new[]
        {
            (Side: AttachSide.Left, Raw: _cliLeft),
            (Side: AttachSide.Right, Raw: _cliRight),
        };
        foreach (var (side, raw) in targets)
        {
            if (string.IsNullOrWhiteSpace(raw)) continue;
            string name = raw.Trim();
            if (name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) name = name[..^4];

            IntPtr hwnd = FindWindowByProcessName(name);
            if (hwnd == IntPtr.Zero)
            {
                ShowNotice($"未找到 {name} 的窗口，已跳过");
                continue;
            }
            if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
            TryAttach(side, hwnd);
        }
    }

    private IntPtr FindWindowByProcessName(string name)
    {
        IntPtr best = IntPtr.Zero;
        long bestArea = -1;
        foreach (var c in WindowLocator.GetCandidates(_handle))
        {
            if (!c.ProcessName.Equals(name, StringComparison.OrdinalIgnoreCase)) continue;
            if (c.Hwnd == _leftHwnd || c.Hwnd == _rightHwnd) continue; // 已吸附的跳过
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
        return Native.GetPid(hwnd) != (uint)Environment.ProcessId;
    }

    internal bool IsAttachedChild(IntPtr hwnd)
        => hwnd != IntPtr.Zero && (hwnd == _leftHwnd || hwnd == _rightHwnd);

    /// <summary>拖放是否被允许：空格、拖回自己、或按住 Ctrl 替换。不允许则不显示高亮。</summary>
    internal bool IsDropAllowed(IntPtr hwnd, int slot)
    {
        IntPtr cur = slot == 0 ? _leftHwnd : _rightHwnd;
        if (cur == IntPtr.Zero || cur == hwnd) return true;
        return IsCtrlHeld();
    }

    internal int HitTestPaneAt(int deviceX, int deviceY)
    {
        if (_handle == IntPtr.Zero || !IsLoaded || WindowState == WindowState.Minimized) return -1;
        var p = PointFromScreen(new Point(deviceX, deviceY));
        double bw = CurBorderW;
        double x0 = bw;
        double x1 = ActualWidth - bw;
        double y0 = bw + TopBarH;
        double y1 = ActualHeight - bw;
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

    /// <summary>
    /// 直角化子窗口（Win11 DWM 圆角是"圆角缝"的根源）：吸附时 DONOTROUND，
    /// 释放时还原 DEFAULT。Win10 无此属性，调用失败无副作用。
    /// </summary>
    private static void SetSquareCorners(IntPtr hwnd, bool square)
    {
        int pref = square ? Native.DWMWCP_DONOTROUND : Native.DWMWCP_DEFAULT;
        Native.DwmSetWindowAttribute(hwnd, Native.DWMWA_WINDOW_CORNER_PREFERENCE, ref pref, sizeof(int));
    }

    /// <summary>持续缓存两个子窗口的 PrintWindow 截图：刷新格子缩略图（任务栏预览用）。</summary>
    private void RefreshChildCaptures()
    {
        _capLeft = CaptureChildSource(_leftHwnd);
        _capRight = CaptureChildSource(_rightHwnd);
        UpdatePaneThumbs();
    }

    /// <summary>把缓存的子窗口截图（裁掉隐形边）填进对应格子的底层 Image。</summary>
    private void UpdatePaneThumbs()
    {
        if (_leftThumb is null) return;
        _leftThumb.Source = PaneThumb(_leftHwnd, _capLeft);
        _rightThumb.Source = PaneThumb(_rightHwnd, _capRight);
    }

    private ImageSource? PaneThumb(IntPtr hwnd, BitmapSource? capture)
    {
        if (hwnd == IntPtr.Zero || capture is null) return null;
        if (!_frameMargins.TryGetValue(hwnd, out var m)) return null;
        int sw = Math.Max(1, capture.PixelWidth - m.L - m.R);
        int sh = Math.Max(1, capture.PixelHeight - m.T - m.B);
        var cropped = new CroppedBitmap(capture, new Int32Rect(m.L, m.T, sw, sh));
        cropped.Freeze();
        return cropped;
    }

    /// <summary>PrintWindow(PW_RENDERFULLCONTENT) 抓取子窗口完整内容（含 Chromium 直合成内容），冻结返回。</summary>
    private BitmapSource? CaptureChildSource(IntPtr hwnd)
    {
        if (!Native.GetWindowRect(hwnd, out var r)) return null;
        int w = r.Width, h = r.Height;
        if (w <= 0 || h <= 0) return null;

        var hdr = new Native.BITMAPINFOHEADER
        {
            biSize = (uint)Marshal.SizeOf<Native.BITMAPINFOHEADER>(),
            biWidth = w,
            biHeight = -h,
            biPlanes = 1,
            biBitCount = 32,
        };
        IntPtr bits;
        IntPtr hbmp = Native.CreateDIBSection(IntPtr.Zero, ref hdr, 0, out bits, IntPtr.Zero, 0);
        if (hbmp == IntPtr.Zero) return null;

        IntPtr hdcMem = Native.CreateCompatibleDC(IntPtr.Zero);
        IntPtr old = Native.SelectObject(hdcMem, hbmp);
        bool ok = Native.PrintWindow(hwnd, hdcMem, Native.PW_RENDERFULLCONTENT);
        Native.SelectObject(hdcMem, old);
        Native.DeleteDC(hdcMem);
        if (!ok)
        {
            Native.DeleteObject(hbmp);
            return null;
        }

        var src = Imaging.CreateBitmapSourceFromHBitmap(hbmp, IntPtr.Zero, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
        Native.DeleteObject(hbmp);
        src.Freeze();
        return src;
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
        if (cur != IntPtr.Zero && !IsCtrlHeld())
        {
            // 占用侧默认不替换；按住 Ctrl 才允许新窗口顶掉旧的
            ShowNotice("该侧已吸附窗口：按住 Ctrl 拖入可替换");
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
        SetSquareCorners(hwnd, square: true);
        if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
        SetToolWindowStyle(hwnd, tool: true);
        if (!ApplyLayoutTo(hwnd, slot))
        {
            // SetWindowPos 被拒：最常见是目标窗口以更高权限运行（UIPI 拦截跨完整性级别操作）
            DetachStateOnly(hwnd);
            ShowNotice("无法吸附：该窗口权限更高（以管理员身份运行 WindowMerger 可解决）");
            return;
        }
        RaiseChildrenBelow();
        UpdateStatus();
        UpdateHostIcon();
    }

    /// <summary>吸附失败时只清理状态，不尝试恢复窗口几何（窗口从未被移动过）。</summary>
    private void DetachStateOnly(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return;
        if (_leftHwnd == hwnd) _leftHwnd = IntPtr.Zero;
        if (_rightHwnd == hwnd) _rightHwnd = IntPtr.Zero;
        _frameMargins.Remove(hwnd);
        _preAttachRects.Remove(hwnd);
        SetSquareCorners(hwnd, square: false);
        SetToolWindowStyle(hwnd, tool: false);
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
        SetSquareCorners(hwnd, square: false); // 圆角还原
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
            ToggleMaximize();
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
        double avail = Math.Max(1, ActualWidth - 2 * CurBorderW - DividerW);
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

    // ---------- 状态栏 ----------

    private void UpdateStatus()
    {
        if (_status is null) return;
        if (_notice is not null && DateTime.UtcNow < _noticeUntil)
        {
            _status.Text = _notice; // 临时通知 3 秒内驻留，不被维护定时器刷掉
        }
        else
        {
            _notice = null;
            if (_leftHwnd == IntPtr.Zero && _rightHwnd == IntPtr.Zero)
            {
                _status.Text = "把任意窗口拖进来吸附，或点顶条 ← / → 选择左/右窗";
            }
            else
            {
                _status.Text = $"左: {PaneTitle(_leftHwnd)}    右: {PaneTitle(_rightHwnd)}";
            }
        }
        UpdateSideButtons();
    }

    private void ShowNotice(string text)
    {
        _notice = text;
        _noticeUntil = DateTime.UtcNow + TimeSpan.FromSeconds(3);
        UpdateStatus();
    }

    private static bool IsCtrlHeld()
        => Keyboard.IsKeyDown(Key.LeftCtrl) || Keyboard.IsKeyDown(Key.RightCtrl);

    /// <summary>左右按钮随格子占用状态翻转：空格=吸附选择，已吸附=释放该侧。</summary>
    private void UpdateSideButtons()
    {
        if (_pickLeftButton is not null)
        {
            bool leftUsed = _leftHwnd != IntPtr.Zero;
            _pickLeftButton.Content = leftUsed ? Icons.ReleasePane : Icons.PickLeft;
            _pickLeftButton.ToolTip = leftUsed ? "释放左窗（回到原位）" : "选择左窗…";
        }
        if (_pickRightButton is not null)
        {
            bool rightUsed = _rightHwnd != IntPtr.Zero;
            _pickRightButton.Content = rightUsed ? Icons.ReleasePane : Icons.PickRight;
            _pickRightButton.ToolTip = rightUsed ? "释放右窗（回到原位）" : "选择右窗…";
        }
    }

    /// <summary>释放指定侧的吸附窗口（回原位、恢复任务栏与圆角）。</summary>
    private void ReleaseSide(int slot)
    {
        if (slot == 0) { DetachRestore(_leftHwnd); _leftHwnd = IntPtr.Zero; }
        else { DetachRestore(_rightHwnd); _rightHwnd = IntPtr.Zero; }
        UpdateStatus();
        UpdateHostIcon();
    }

    private static string PaneTitle(IntPtr hwnd)
        => hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) ? "空" : Truncate(Native.GetTitle(hwnd), 40);

    private static string Truncate(string s, int max)
        => s.Length <= max ? s : s[..(max - 1)] + "…";
}
