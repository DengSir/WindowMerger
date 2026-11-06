using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace WindowMerger;

public sealed partial class HostWindow : Window
{
    // 布局尺寸单一来源是 HostWindow.xaml（外框 BorderThickness / 顶条 Height / 分隔条列宽），
    // WireUi 时从 UI 读入这里，代码不再手工维护同值常量
    private double _borderW;    // 外框宽（最大化时隐藏为 0）
    private double _topBarH;    // 顶条高度
    private double _dividerW;   // 中间分隔条宽度

    private const double MinRatio = 0.2;
    private const double MaxRatio = 0.8;

    private const int WM_GETMINMAXINFO = 0x0024;
    private const int WM_SETTINGCHANGE = 0x001A;

    private double _ratio;

    private IntPtr _handle;
    private AttachedChild? _left;    // 左格当前吸附态（null=空格）
    private AttachedChild? _right;   // 右格当前吸附态
    private readonly HashSet<long> _attachedPids = new();
    private DragAttach? _drag;
    private readonly DispatcherTimer _timer;
    private Point _lastOrigin;
    private int _highlightSlot = -1;
    private string? _notice;
    private DateTime _noticeUntil;

    /// <summary>当前生效的边框宽度：最大化时边框隐藏，格子铺满窗口。</summary>
    private double CurBorderW => WindowState == WindowState.Maximized ? 0 : _borderW;

    /// <summary>槽位 → 吸附态（null=空格）。</summary>
    private AttachedChild? ChildAt(int slot) => slot == 0 ? _left : _right;

    private IntPtr HwndOf(int slot) => ChildAt(slot)?.Hwnd ?? IntPtr.Zero;

    /// <summary>侧按钮点击：空格=打开选择器吸附，已吸附=释放该侧。</summary>
    private void ToggleSide(int slot)
    {
        if (HwndOf(slot) == IntPtr.Zero) Pick(slot == 0 ? AttachSide.Left : AttachSide.Right);
        else ReleaseSide(slot);
    }

    public HostWindow(AppConfig config, string? cliLeft = null, string? cliRight = null)
    {
        if (Enum.TryParse<AppThemeMode>(config.Theme, true, out var mode)) AppTheme.Mode = mode;
        _ratio = Math.Clamp(config.Ratio, MinRatio, MaxRatio);
        var orphanPids = config.AttachedPids;
        var orphanHwnds = config.AttachedHwnds;

        InitializeComponent();

        // 尺寸/位置是配置驱动的，必须在 InitializeComponent 之后覆盖
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

        WireUi();
        ApplyTheme(); // XAML 只带深色初值，按配置主题重刷一遍（含按钮前景）

        LocationChanged += (_, _) => OnHostMoved();
        SizeChanged += (_, _) => { UpdatePaneWidths(); ApplyLayout(); };
        StateChanged += (_, _) => OnStateChanged();
        Activated += (_, _) =>
        {
            ShowAttachedChildren();
            RaiseChildrenBelow();
            // 宿主激活把宿主单独升到 z 序顶端，子窗口留在原地；低优先级再插回一次加固
            Dispatcher.BeginInvoke(RaiseChildrenBelow, DispatcherPriority.Background);
        };
        DpiChanged += (_, _) => ApplyLayout();
        Loaded += (_, _) => { UpdatePaneWidths(); ApplyLayout(); CleanupOrphanedToolWindows(orphanPids, orphanHwnds); AttachStartupTargets(cliLeft, cliRight); };
        Closing += (_, _) => OnClosingCleanup();

        _timer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(250),
        };
        _timer.Tick += (_, _) => Maintain();
    }

    // ---------- UI ----------

    /// <summary>视觉树在 HostWindow.xaml；这里只补齐动态部分：字形内容、点击、条件可见性。</summary>
    private void WireUi()
    {
        // 布局尺寸单一来源 = XAML；这里读入，几何公式不再手工维护同值常量
        _borderW = _outer.BorderThickness.Left;
        _topBarH = _topBar.Height;
        _dividerW = _content.ColumnDefinitions[1].Width.Value;

        _divider.MouseLeftButtonDown += DividerOnMouseDown;
        _divider.MouseMove += DividerOnMouseMove;
        _divider.MouseLeftButtonUp += DividerOnMouseUp;

        // 顶条左端应用图标
        _appIcon.Source = LoadAppIconFrame();

        // 顶条功能组：[左][右][交换][释放][主题] | [─][□][✕]
        // 静态字形直接写在 XAML；这里只挂接点击与动态字形（主题月亮/太阳、最大化/还原）
        _pickLeftButton.Click += (_, _) => ToggleSide(0);
        _pickRightButton.Click += (_, _) => ToggleSide(1);
        _swapButton.Click += (_, _) => SwapSides();
        _releaseButton.Click += (_, _) => ReleaseAll();
        _themeButton.Content = ThemeGlyph();
        _themeButton.Click += (_, _) => OpenThemeMenu();
        _minimizeButton.Click += (_, _) => WindowState = WindowState.Minimized;
        _maxButton.Click += (_, _) => ToggleMaximize();
        _closeButton.Click += (_, _) => Close();
        UpdateMaxGlyph(); // 初始字体/内容配对：f096 空心方块必须配 Regular 字体（solid 里有同码位实心别名）

        _topBar.MouseLeftButtonDown += TopBarOnMouseDown;
        _topBar.MouseMove += TopBarOnMouseMove;
        _topBar.MouseLeftButtonUp += TopBarOnMouseUp;
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
        return $"主题：{state}，点击选择";
    }

    /// <summary>主题按钮下拉菜单：直接选择 跟随系统/深色/浅色（替代循环切换）。</summary>
    private void OpenThemeMenu()
    {
        var p = AppTheme.Current();
        // 默认 ContextMenu 模板里有一层不随主题的白色圆角内边框，必须整体替换为
        // 极简模板（Border+ItemsPresenter），配色才完全由当前主题决定
        var menuTemplate = new ControlTemplate(typeof(ContextMenu));
        var menuBorder = new FrameworkElementFactory(typeof(Border));
        menuBorder.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(ContextMenu.BackgroundProperty));
        menuBorder.SetValue(Border.BorderBrushProperty, new TemplateBindingExtension(ContextMenu.BorderBrushProperty));
        menuBorder.SetValue(Border.BorderThicknessProperty, new TemplateBindingExtension(ContextMenu.BorderThicknessProperty));
        menuBorder.SetValue(Border.PaddingProperty, new TemplateBindingExtension(ContextMenu.PaddingProperty));
        menuBorder.AppendChild(new FrameworkElementFactory(typeof(ItemsPresenter)));
        menuTemplate.VisualTree = menuBorder;

        var menu = new ContextMenu
        {
            Template = menuTemplate,
            Background = AppTheme.Brush(p.Bar),
            BorderBrush = AppTheme.Brush(p.Border),
            BorderThickness = new Thickness(1),
            Padding = new Thickness(4),
            PlacementTarget = _themeButton,
            Placement = System.Windows.Controls.Primitives.PlacementMode.Bottom,
        };
        menu.Items.Add(ThemeMenuItem("跟随系统", AppThemeMode.Auto, p));
        menu.Items.Add(ThemeMenuItem("深色", AppThemeMode.Dark, p));
        menu.Items.Add(ThemeMenuItem("浅色", AppThemeMode.Light, p));
        menu.IsOpen = true;
    }

    private MenuItem ThemeMenuItem(string label, AppThemeMode mode, AppTheme.Palette p)
    {
        // 极简模板只呈现 Background（默认模板的浅灰高亮会破坏深色主题），悬停色事件时从当前主题取
        var template = new ControlTemplate(typeof(MenuItem));
        var border = new FrameworkElementFactory(typeof(Border));
        border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(MenuItem.BackgroundProperty));
        border.SetValue(Border.PaddingProperty, new TemplateBindingExtension(MenuItem.PaddingProperty));
        var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
        presenter.SetValue(ContentPresenter.ContentSourceProperty, "Header"); // MenuItem 无 Content 属性，必须显式指到 Header
        presenter.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
        border.AppendChild(presenter);
        template.VisualTree = border;

        var item = new MenuItem
        {
            Header = (AppTheme.Mode == mode ? "✓ " : "　 ") + label,
            Background = Brushes.Transparent,
            Foreground = AppTheme.Brush(p.Text),
            BorderThickness = new Thickness(0),
            Padding = new Thickness(12, 6, 20, 6),
            FontSize = 12,
            Template = template,
        };
        item.MouseEnter += (_, _) => item.Background = AppTheme.Brush(AppTheme.Current().ButtonHover);
        item.MouseLeave += (_, _) => item.Background = Brushes.Transparent;
        item.Click += (_, _) =>
        {
            AppTheme.Mode = mode;
            ApplyTheme();
            SaveConfig();
        };
        return item;
    }

    private void ApplyTheme()
    {
        var p = AppTheme.Current();
        // 主题刷色 = 换资源：所有 DynamicResource 引用（顶条/格子/分隔条/文字/边框）自动跟随，
        // 无需逐元素赋值；按钮悬停色仍由 MouseEnter 现场从 AppTheme 取
        Resources["ThemeBarBrush"] = AppTheme.Brush(p.Bar);
        Resources["ThemeBorderBrush"] = AppTheme.Brush(p.Border);
        Resources["ThemeDividerBrush"] = AppTheme.Brush(p.Divider);
        Resources["ThemeDividerHoverBrush"] = AppTheme.Brush(p.DividerHover);
        Resources["ThemeTextBrush"] = AppTheme.Brush(p.Text);
        Resources["ThemeButtonHoverBrush"] = AppTheme.Brush(p.ButtonHover);
        Resources["ThemeDangerHoverBrush"] = AppTheme.Brush(p.DangerHover);
        _themeButton.Content = ThemeGlyph();
        _themeButton.ToolTip = ThemeTooltip();
    }

    private void SaveConfig()
    {
        var cfg = new AppConfig { Ratio = _ratio, Theme = AppTheme.Mode.ToString() };
        cfg.AttachedPids = _attachedPids.ToList();
        cfg.AttachedHwnds = new[] { _left, _right }
            .Where(c => c is not null)
            .Select(c => c!.Hwnd.ToInt64())
            .ToList();
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

    private void UpdateMaxGlyph()
    {
        // 字体固定 FaRegular（XAML），只切换字形：f096 空心方块 ↔ f24d 空心 clone
        // （注意 f096 在 solid 里有同码位实心别名，必须配 Regular 才是空心）
        if (WindowState == WindowState.Maximized)
        {
            _maxButton.Content = "\uF24D";
        }
        else
        {
            _maxButton.Content = "\uF096";
        }
    }

    private void ToggleMaximize()
        => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    // ---------- 生命周期 ----------

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        _handle = new WindowInteropHelper(this).Handle;
        HwndSource.FromHwnd(_handle)!.AddHook(WndProc);
        _lastOrigin = PointToScreen(new Point(0, 0));
        _drag = new DragAttach(this);
        _timer.Start();
        SetFallbackIcon();
    }

    /// <summary>从内嵌 ico 资源流解码最大帧（窗口图标与顶条图标共用）。</summary>
    private static BitmapSource? LoadAppIconFrame()
    {
        try
        {
            var rs = System.Windows.Application.GetResourceStream(
                new Uri("pack://application:,,,/assets/WindowMerger.ico"));
            if (rs == null) return null;
            var decoder = BitmapDecoder.Create(rs.Stream, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
            BitmapSource? best = null;
            foreach (var frame in decoder.Frames)
            {
                if (best == null || frame.PixelWidth * frame.PixelHeight > best.PixelWidth * best.PixelHeight)
                {
                    best = frame;
                }
            }
            best?.Freeze();
            return best;
        }
        catch (Exception)
        {
            // 图标资源缺失/损坏只影响外观，按设计降级
            return null;
        }
    }

    /// <summary>
    /// 应用图标作为窗口基础图标：未吸附子窗口时任务栏/Alt+Tab 显示它，
    /// 吸附后由 UpdateHostIcon 换成双子窗口合成图标。
    /// </summary>
    private void SetFallbackIcon()
    {
        if (LoadAppIconFrame() is { } icon)
        {
            Icon = icon;
        }
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
            mmi.ptMinTrackSize.X = (int)MinWidth;
            mmi.ptMinTrackSize.Y = (int)MinHeight;
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

        foreach (var child in new[] { _left, _right })
        {
            if (child is null || !child.IsAlive || Native.IsIconic(child.Hwnd)) continue;
            if (!Native.GetWindowRect(child.Hwnd, out var r)) continue;
            Native.SetWindowPos(child.Hwnd, IntPtr.Zero, r.Left + dx, r.Top + dy, 0, 0,
                Native.SWP_NOSIZE | Native.SWP_NOACTIVATE | Native.SWP_NOZORDER);
        }
    }

    private void ApplyLayout()
    {
        if (_handle == IntPtr.Zero || !IsLoaded) return;
        ApplyLayoutTo(_left, 0);
        ApplyLayoutTo(_right, 1);
    }

    private bool ApplyLayoutTo(AttachedChild? child, int slot)
    {
        if (child is null || !Native.IsWindow(child.Hwnd) || Native.IsIconic(child.Hwnd) || Native.IsZoomed(child.Hwnd)) return false;
        if (ActualWidth < 50 || ActualHeight < 50) return false;
        IntPtr hwnd = child.Hwnd;

        var (x, y, w, h) = PaneRectDevice(slot);

        // 外扩 DWM 隐形边，可见内容才能精确填满格子
        var m = child.FrameMargins;
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
        // 插到宿主正下方（相对插入是稳定语义）：宿主不透明部分（分隔条/边框）盖住子窗口
        // 隐形边可点击，透明格子透出子窗口。不要用 HWND_TOP——实测 Alt+Tab 切回宿主后
        // 它是静默无效调用（返回 true 但 z 序不变，子窗口被切走前的窗口一直压住）
        return Native.SetWindowPos(hwnd, _handle, x, y, w, h,
            Native.SWP_NOACTIVATE);
    }

    private (int X, int Y, int W, int H) PaneRectDevice(int slot)
    {
        double bw = CurBorderW;
        double availDip = Math.Max(0, ActualWidth - 2 * bw - _dividerW);
        double contentHDip = Math.Max(0, ActualHeight - 2 * bw - _topBarH);
        double leftWDip = availDip * _ratio;
        double xDip = slot == 0 ? bw : bw + leftWDip + _dividerW;
        double wDip = slot == 0 ? leftWDip : availDip - leftWDip;

        var tl = PointToScreen(new Point(xDip, bw + _topBarH));
        var br = PointToScreen(new Point(xDip + wDip, bw + _topBarH + contentHDip));
        return ((int)Math.Round(tl.X), (int)Math.Round(tl.Y),
                (int)Math.Round(br.X - tl.X), (int)Math.Round(br.Y - tl.Y));
    }

    private void UpdatePaneWidths()
    {
        // 用窗口 ActualWidth 直算（与 PaneRectDevice 同一公式），不能用 _content.ActualWidth——
        // 最大化还原时 StateChanged 早于尺寸回缩完成，读到的旧值会把分隔条顶到错误位置
        double avail = Math.Max(0, ActualWidth - 2 * CurBorderW - _dividerW);
        _leftCol.Width = new GridLength(avail * _ratio);
    }

    private void RaiseChildrenBelow()
    {
        if (_handle == IntPtr.Zero) return;
        // 插到宿主正下方（先右后左，最终顺序上→下：宿主、左、右）。
        // 不用 HWND_TOP：实测 Alt+Tab 切回宿主后它是静默无效调用（返回 true 但 z 序不变）
        foreach (var child in new[] { _right, _left })
        {
            if (child is null || !Native.IsWindow(child.Hwnd) || Native.IsIconic(child.Hwnd)) continue;
            Native.SetWindowPos(child.Hwnd, _handle, 0, 0, 0, 0,
                Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE);
        }
    }

    private void FixZOrder()
    {
        // 宿主正下方必须是连续的子窗口块（次序不限）：Alt+Tab 切回时宿主单独升顶，
        // 子窗口留在原地会被切走前的前台窗口压住（宿主内 HWND_TOP 拉起实测无效）。
        // 不满足就整体插回宿主正下方。最小化（移出屏幕外但非 iconic）的子窗口豁免。
        IntPtr below = _handle == IntPtr.Zero ? IntPtr.Zero : Native.GetWindow(_handle, Native.GW_HWNDNEXT);
        bool leftOk = false, rightOk = false;
        for (int i = 0; i < 2 && below != IntPtr.Zero; i++)
        {
            if (_left is not null && below == _left.Hwnd) leftOk = true;
            if (_right is not null && below == _right.Hwnd) rightOk = true;
            below = Native.GetWindow(below, Native.GW_HWNDNEXT);
        }
        bool needLeft = _left is not null && _left.IsAlive && !Native.IsIconic(_left.Hwnd) && !leftOk;
        bool needRight = _right is not null && _right.IsAlive && !Native.IsIconic(_right.Hwnd) && !rightOk;
        if (needLeft || needRight) RaiseChildrenBelow();
    }

    private void Maintain()
    {
        bool childLost = false;
        if (_left is not null && !_left.IsAlive) { _left = null; childLost = true; }
        if (_right is not null && !_right.IsAlive) { _right = null; childLost = true; }
        UpdateStatus();
        if (childLost) { UpdateHostIcon(); }

        if (WindowState == WindowState.Minimized) return; // 最小化时不布局；最大化也要自愈
        bool dragging = _drag is { IsBusy: true };
        if (!dragging && _highlightSlot != -1) SetDragHighlight(-1); // 拖动事件丢失时兜底熄灭高亮
        if (dragging) return; // 有窗口正在被拖动，不对抗

        // 应用自身可能被外部改回普通样式（个别框架会重写样式），丢失时补上；
        // 吸附子窗口没有任务栏按钮，最小化后无从手动还原；独立最大化则摧毁合并布局——
        // 宿主可见期间两种状态一律拉回格子自愈（子窗口自身没有"最大化"概念）
        foreach (var child in new[] { _left, _right })
        {
            child?.EnsureDockedState();
        }

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
                // 子窗口是 tool window，最小化会缩成标题条留在桌面左下——直接移出屏幕外
                // （对所有窗口类型有效，还原时 ApplyLayout 按格子矩形拉回）
                foreach (var child in new[] { _left, _right })
                {
                    if (child is null || !Native.IsWindow(child.Hwnd)) continue;
                    Native.SetWindowPos(child.Hwnd, IntPtr.Zero, -32000, -32000, 0, 0,
                        Native.SWP_NOSIZE | Native.SWP_NOACTIVATE | Native.SWP_NOZORDER);
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
    /// 宿主回到可见状态时恢复所有子窗口的可见性（隐藏的最小化联动子窗口、
    /// 被独立最小化/最大化的子窗口一律拉回格子）。
    /// 子窗口是 tool window 没有任务栏按钮，不在这里还原就永远回不来；
    /// 最大化路径尤其必要：从最大化最小化后点任务栏还原直接进 Maximized，不经过 Normal。
    /// </summary>
    private void ShowAttachedChildren()
    {
        foreach (var child in new[] { _left, _right })
        {
            if (child is null || !Native.IsWindow(child.Hwnd)) continue;
            if (Native.IsIconic(child.Hwnd) || Native.IsZoomed(child.Hwnd))
            {
                Native.ShowWindow(child.Hwnd, Native.SW_RESTORE);
            }
            else if (!Native.IsWindowVisible(child.Hwnd))
            {
                Native.ShowWindow(child.Hwnd, Native.SW_SHOWNA);
            }
        }
    }

    /// <summary>
    /// 启动时清理上一会话的孤儿：宿主被强杀时已吸附子窗口会残留
    /// WS_EX_TOOLWINDOW（任务栏消失、可能停在屏幕外），按记录的 HWND 精确摘除样式。
    /// 不能按 PID 枚举：进程的隐藏辅助窗口（CiceroUIWndFrame 等）同样带 TOOLWINDOW，
    /// 误显示会产生"点不出来的任务栏幽灵按钮"（实测踩坑）。PID 仅用于句柄复用校验。
    /// </summary>
    private static void CleanupOrphanedToolWindows(List<long>? pids, List<long>? hwnds)
    {
        if (hwnds is not { Count: > 0 } || pids is not { Count: > 0 }) return;
        var pidSet = pids.ToHashSet();
        foreach (var raw in hwnds)
        {
            var h = new IntPtr(raw);
            if (!Native.IsWindow(h)) continue;
            Native.GetWindowThreadProcessId(h, out uint pid);
            if (!pidSet.Contains(pid)) continue; // 句柄已被复用给其他进程，跳过
            int ex = Native.GetWindowLong(h, Native.GWL_EXSTYLE);
            if ((ex & Native.WS_EX_TOOLWINDOW) == 0) continue; // 已还原（正常释放过）
            Native.SetWindowLong(h, Native.GWL_EXSTYLE, ex & ~Native.WS_EX_TOOLWINDOW);
            Native.ShowWindow(h, Native.SW_SHOWNA); // 任务栏重新收录
            if (Native.GetWindowRect(h, out var r) && (r.Left <= -30000 || r.Top <= -30000))
            {
                // 宿主最小化联动时被强杀：窗口还停在移出屏幕外的位置，拉回工作区
                Native.SetWindowPos(h, IntPtr.Zero, 60, 60, 1200, 800, Native.SWP_NOZORDER);
            }
        }
    }

    // ---------- 吸附 ----------

    /// <summary>
    /// 命令行吸附：WindowMerger.exe [左进程名|左PID] [右进程名|右PID]，Loaded 后执行一次。
    /// 参数为纯数字时按 PID 匹配（脚本 Start-Process -PassThru 可直接拿到），否则按进程名
    /// （可带可不带 .exe，大小写不敏感）；同候选多窗口取面积最大的；
    /// 未找到的跳过并在状态栏提示；已吸附的 hwnd 去重。
    /// </summary>
    private void AttachStartupTargets(string? cliLeft, string? cliRight)
    {
        if (cliLeft is null && cliRight is null) return;

        var targets = new[]
        {
            (Side: AttachSide.Left, Raw: cliLeft),
            (Side: AttachSide.Right, Raw: cliRight),
        };
        foreach (var (side, raw) in targets)
        {
            if (string.IsNullOrWhiteSpace(raw)) continue;
            string arg = raw.Trim();

            IntPtr hwnd = FindWindowByArg(arg);
            if (hwnd == IntPtr.Zero)
            {
                ShowNotice($"未找到 {arg} 的窗口，已跳过");
                continue;
            }
            if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
            TryAttach(side, hwnd);
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
        return Native.GetPid(hwnd) != (uint)Environment.ProcessId;
    }

    internal bool IsAttachedChild(IntPtr hwnd)
        => hwnd != IntPtr.Zero && (hwnd == (_left?.Hwnd ?? IntPtr.Zero) || hwnd == (_right?.Hwnd ?? IntPtr.Zero));

    /// <summary>拖放是否被允许：空格、拖回自己、或按住 Ctrl 替换。不允许则不显示高亮。</summary>
    internal bool IsDropAllowed(IntPtr hwnd, int slot)
    {
        IntPtr cur = HwndOf(slot);
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
        double y0 = bw + _topBarH;
        double y1 = ActualHeight - bw;
        if (p.X < x0 || p.X > x1 || p.Y < y0 || p.Y > y1) return -1;
        double avail = Math.Max(1, _content.ActualWidth - _dividerW);
        double split = x0 + avail * _ratio + _dividerW / 2;
        return p.X < split ? 0 : 1;
    }

    internal void SetDragHighlight(int slot)
    {
        _highlightSlot = slot;
        _leftGlow.Visibility = slot == 0 ? Visibility.Visible : Visibility.Collapsed;
        _rightGlow.Visibility = slot == 1 ? Visibility.Visible : Visibility.Collapsed;
    }

    // ---------- 任务栏隐藏与图标叠加 ----------

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
        var l = TryGetIconSource(_left?.Hwnd ?? IntPtr.Zero);
        var r = TryGetIconSource(_right?.Hwnd ?? IntPtr.Zero);
        if (l == null && r == null)
        {
            SetFallbackIcon(); // 无吸附窗口时回到应用图标（而非默认 WPF 图标）
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

        // 两枚图标对角叠放：右窗右上靠后（先画在下），左窗左下靠前（后画盖在上面）
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            dc.DrawImage(r, new Rect(8, 0, 24, 24));
            dc.DrawImage(l, new Rect(0, 8, 24, 24));
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
        var child = ChildAt(slot);
        var other = ChildAt(1 - slot);
        IntPtr cur = child?.Hwnd ?? IntPtr.Zero;
        IntPtr otherHwnd = other?.Hwnd ?? IntPtr.Zero;

        if (hwnd == cur)
        {
            ApplyLayoutTo(child, slot); // 拖走又拖回来：吸附回原格
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
            // 拖到另一侧 = 换到另一侧（吸附态整体搬家）
            if (slot == 0) { _right = _left; _left = null; }
            else { _left = _right; _right = null; }
            ApplyLayoutTo(ChildAt(slot), slot);
            UpdateStatus();
            return;
        }

        if (child is not null) child.Restore(); // 替换：原窗口回到吸附前位置
        var attached = AttachedChild.Attach(hwnd);
        if (slot == 0) _left = attached; else _right = attached;
        Native.SetSquareCorners(hwnd, square: true);
        if (Native.IsIconic(hwnd)) Native.ShowWindow(hwnd, Native.SW_RESTORE);
        Native.SetToolWindowStyle(hwnd, tool: true);
        _attachedPids.Add(Native.GetPid(hwnd));
        if (!ApplyLayoutTo(attached, slot))
        {
            // SetWindowPos 被拒：最常见是目标窗口以更高权限运行（UIPI 拦截跨完整性级别操作）
            DetachStateOnly(slot, attached);
            ShowNotice("无法吸附：该窗口权限更高（以管理员身份运行 WindowMerger 可解决）");
            return;
        }
        RaiseChildrenBelow();
        UpdateStatus();
        UpdateHostIcon();
        SaveConfig(); // 吸附即落盘：宿主被强杀时孤儿清理才有 HWND 可循
    }

    /// <summary>吸附失败时只清理状态，不尝试恢复窗口几何（窗口从未被移动过）。</summary>
    private void DetachStateOnly(int slot, AttachedChild child)
    {
        if (ChildAt(slot) == child)
        {
            if (slot == 0) _left = null; else _right = null;
        }
        Native.SetSquareCorners(child.Hwnd, square: false);
        Native.SetToolWindowStyle(child.Hwnd, tool: false);
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

    private double _maxDragOffX, _maxDragOffY; // 拖动锚点：光标相对还原窗口左上角的设备像素偏移（按整窗比例）
    private bool _maxDragArmed;     // 已按下、未超过拖动阈值
    private bool _maxDragActive;    // 已还原，手动拖动进行中

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

    private Point _maxDragGrabPoint;

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
            if (_left is null && _right is null)
            {
                _status.Text = "把任意窗口拖进来吸附，或点顶条 ← / → 选择左/右窗";
            }
            else
            {
                _status.Text = $"左: {PaneTitle(_left?.Hwnd ?? IntPtr.Zero)}    右: {PaneTitle(_right?.Hwnd ?? IntPtr.Zero)}";
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

    /// <summary>左右按钮随格子占用状态翻转：空格=吸附选择（f060/f061），已吸附=释放该侧（f2d2）。</summary>
    private void UpdateSideButtons()
    {
        var sides = new[] { (_pickLeftButton, HwndOf(0)), (_pickRightButton, HwndOf(1)) };
        foreach (var (btn, hwnd) in sides)
        {
            bool used = hwnd != IntPtr.Zero;
            btn.Content = used ? "\uF2D2" : "\uF060";
            btn.ToolTip = used ? "释放该侧（回到原位）" : "选择该侧…";
        }
    }

    /// <summary>释放指定侧的吸附窗口（回原位、恢复任务栏与圆角）。</summary>
    private void ReleaseSide(int slot)
    {
        ChildAt(slot)?.Restore();
        if (slot == 0) _left = null; else _right = null;
        UpdateStatus();
        UpdateHostIcon();
    }

    private static string PaneTitle(IntPtr hwnd)
        => hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) ? "空" : Truncate(Native.GetTitle(hwnd), 40);

    private static string Truncate(string s, int max)
        => s.Length <= max ? s : s[..(max - 1)] + "…";
}
