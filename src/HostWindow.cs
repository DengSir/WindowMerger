using System.Diagnostics;
using System.IO;
using System.Reflection;
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
    // 待落位的保存几何（物理像素）：hwnd 建好后 OnSourceInitialized 用 SetWindowPos 写入——
    // 不能在 hwnd 前设 DIP 属性（WPF 按初始主屏 DPI 解释，跨屏落位漂移）
    private (double X, double Y, double W, double H, bool Maximized)? _pendingPlacement;
    private DragAttach? _drag;
    private readonly DispatcherTimer _timer;
    private Point _lastOrigin;
    private AttachSide? _highlight;   // 当前拖放高亮的槽位（null=无）
    private string? _notice;
    private DateTime _noticeUntil;

    /// <summary>当前生效的边框宽度：最大化时边框隐藏，格子铺满窗口。</summary>
    private double CurBorderW => WindowState == WindowState.Maximized ? 0 : _borderW;

    /// <summary>槽位 → 吸附态（null=空格）。</summary>
    private AttachedChild? ChildAt(AttachSide side) => side == AttachSide.Left ? _left : _right;

    private IntPtr HwndOf(AttachSide side) => ChildAt(side)?.Hwnd ?? IntPtr.Zero;

    /// <summary>解析保存的几何（物理像素）为启动落位矩形；无效（无保存/垃圾值）返回 null（默认居中）。
    /// 目标屏 = 保存矩形中心最近的可见显示器（断屏/改分辨率时自然回拉），尺寸与位置都钳到其工作区。</summary>
    private (double X, double Y, double W, double H, bool Maximized)? ResolvePlacement(AppConfig config)
    {
        // 无保存矩形或垃圾值（L>=R / T>=B）
        if (config.WinLeft is not double l || config.WinTop is not double t
            || config.WinRight is not double r || config.WinBottom is not double b
            || r <= l || b <= t)
        {
            return null;
        }

        var center = new Native.POINT { X = (int)((l + r) / 2), Y = (int)((t + b) / 2) };
        nint hMon = Native.MonitorFromPoint(center, Native.MONITOR_DEFAULTTONEAREST);
        var mi = new Native.MONITORINFO { cbSize = Marshal.SizeOf<Native.MONITORINFO>() };
        if (!Native.GetMonitorInfo(hMon, ref mi)) return null;
        var wa = mi.rcWork; // 物理 px

        // 尺寸钳制：小于最小尺寸（按目标屏 DPI 换算）/ 大于工作区都修正
        double scale = Native.MonitorDpiScale(hMon);
        double minW = MinWidth * scale, minH = MinHeight * scale;
        double w = Math.Clamp(r - l, minW, Math.Max(minW, wa.Right - wa.Left));
        double h = Math.Clamp(b - t, minH, Math.Max(minH, wa.Bottom - wa.Top));
        // 位置钳制：矩形完整落在工作区内（任何一边都不出屏）
        double x = Math.Clamp(l, wa.Left, Math.Max(wa.Left, wa.Right - w));
        double y = Math.Clamp(t, wa.Top, Math.Max(wa.Top, wa.Bottom - h));
        return (x, y, w, h, config.WinMaximized);
    }

    /// <summary>侧按钮点击：空格=打开选择器吸附，已吸附=释放该侧。</summary>
    private void ToggleSide(AttachSide side)
    {
        if (HwndOf(side) == IntPtr.Zero) Pick(side);
        else ReleaseSide(side);
    }

    public HostWindow(AppConfig config, string? cliLeft = null, string? cliRight = null,
        string? cliLeftExe = null, string? cliRightExe = null)
    {
        if (Enum.TryParse<AppThemeMode>(config.Theme, true, out var mode)) AppTheme.Mode = mode;
        _ratio = Math.Clamp(config.Ratio, MinRatio, MaxRatio);
        var orphanPids = config.AttachedPids;
        var orphanHwnds = config.AttachedHwnds;

        InitializeComponent();

        // 几何恢复（Windows 原生惯例）：正常态矩形（物理像素）+ 是否最大化，校验钳制到
        // 可见显示器工作区后暂存，hwnd 建好后 OnSourceInitialized 落位——显示器断开/
        // 分辨率变化/配置损坏都不能产生屏外幽灵窗。无有效几何默认 1280×800 主屏居中
        _pendingPlacement = ResolvePlacement(config);
        Width = 1280;
        Height = 800;
        // hwnd 建好前的初始值（无有效几何时即最终状态）；有保存几何时 OnSourceInitialized
        // 用 SetWindowPos 写物理像素落位，绕开 WPF 对 DIP 属性的初始主屏 DPI 解释

        WireUi();
        ApplyTheme(); // XAML 只带深色初值，按配置主题重刷一遍（含按钮前景）

        LocationChanged += (_, _) => OnHostMoved();
        SizeChanged += (_, _) => { UpdatePaneWidths(); ApplyLayout(); };
        StateChanged += (_, _) => OnStateChanged();
        Activated += (_, _) =>
        {
            foreach (var child in new[] { _left, _right })
            {
                child?.EnsureDockedState();
            }
            RaiseChildrenBelow();
            // 宿主激活把宿主单独升到 z 序顶端，子窗口留在原地；低优先级再插回一次加固
            Dispatcher.BeginInvoke(RaiseChildrenBelow, DispatcherPriority.Background);
        };
        DpiChanged += (_, _) => ApplyLayout();
        Loaded += (_, _) => { UpdatePaneWidths(); ApplyLayout(); CleanupOrphanedToolWindows(orphanPids, orphanHwnds); AttachStartupTargets(cliLeft, cliRight, cliLeftExe, cliRightExe); };
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
        _pickLeftButton.Click += (_, _) => ToggleSide(AttachSide.Left);
        _pickRightButton.Click += (_, _) => ToggleSide(AttachSide.Right);
        _swapButton.Click += (_, _) => SwapSides();
        _releaseButton.Click += (_, _) => ReleaseAll();
        _shortcutButton.Click += (_, _) => CreateShortcutForCurrent();
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

        // 选中标志 = Font Awesome 对勾（固定宽度占位，未选中留空但保持文字对齐），
        // 与顶条按钮同一内嵌字体族；pack 字体必须经 XAML 声明，这里只取资源引用
        var header = new StackPanel { Orientation = Orientation.Horizontal };
        header.Children.Add(new TextBlock
        {
            Text = AppTheme.Mode == mode ? "\uF00C" : "",
            FontFamily = (FontFamily)FindResource("FaSolid"),
            FontSize = 10,
            Width = 20,
            VerticalAlignment = VerticalAlignment.Center,
        });
        header.Children.Add(new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center });

        var item = new MenuItem
        {
            Header = header,
            Background = Brushes.Transparent,
            Foreground = AppTheme.Brush(p.Text),
            BorderThickness = new Thickness(0),
            Padding = new Thickness(6, 6, 20, 6),
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

    // ---------- 快捷方式 ----------

    /// <summary>按当前吸附生成桌面快捷方式：参数用进程名（重启后仍能复现组合），PID 易失不入参；
    /// 另记录各侧 exe 完整路径（--left-exe/--right-exe），双击时目标未运行可自动拉起再吸附。
    /// 提权/受保护进程取不到路径，降级为仅名字。</summary>
    private void CreateShortcutForCurrent()
    {
        string? left = ProcessNameOfChild(_left);
        string? right = ProcessNameOfChild(_right);
        if (left is null && right is null)
        {
            ShowNotice("未吸附窗口：先吸附再创建快捷方式");
            return;
        }

        string? leftExe = ImagePathOfChild(_left);
        string? rightExe = ImagePathOfChild(_right);

        var argv = new List<string>();
        if (left is not null)
        {
            argv.Add($"--left \"{left}\"");
            if (leftExe is not null) argv.Add($"--left-exe \"{leftExe}\"");
        }
        if (right is not null)
        {
            argv.Add($"--right \"{right}\"");
            if (rightExe is not null) argv.Add($"--right-exe \"{rightExe}\"");
        }
        string display = string.Join(" + ", new[] { left, right }.Where(n => n is not null));

        // 文件名剔除非法字符（进程名源自 exe 文件名，防御性处理）
        string safe = string.Concat(display.Split(Path.GetInvalidFileNameChars()));
        string path = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            $"窗口合并 - {safe}.lnk");
        try
        {
            CreateShortcut(path, string.Join(" ", argv), $"窗口合并：{display}");
            ShowNotice($"已创建桌面快捷方式：{display}");
        }
        catch (Exception ex)
        {
            // 用户触发的动作失败不上抛崩宿主，状态栏报因；WScript.Shell 经反射调用，
            // 真实原因包在 TargetInvocationException.InnerException 里（CI 实测只见外层）
            var reason = ex is System.Reflection.TargetInvocationException tie
                && tie.InnerException is not null
                ? tie.InnerException.Message : ex.Message;
            ShowNotice($"创建快捷方式失败：{reason}");
        }
    }

    private static string? ProcessNameOfChild(AttachedChild? child)
    {
        if (child is null || !child.IsAlive) return null;
        try
        {
            return Process.GetProcessById((int)child.Pid).ProcessName;
        }
        catch (ArgumentException)
        {
            return null; // 进程已退出
        }
    }

    /// <summary>子窗口进程的 exe 完整路径；进程打不开（提权/受保护）、查询失败或已退出返回 null。
    /// 用户触发的快捷方式生成走这里，任何异常都不上抛（降级为仅进程名，不崩宿主）。</summary>
    private static string? ImagePathOfChild(AttachedChild? child)
    {
        if (child is null || !child.IsAlive) return null;
        try
        {
            return Native.GetProcessImagePath(child.Pid);
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>经 WScript.Shell COM 写 .lnk（反射调用，不走 dynamic，免去 Microsoft.CSharp 依赖）。</summary>
    private static void CreateShortcut(string path, string arguments, string description)
    {
        var shellType = Type.GetTypeFromProgID("WScript.Shell")
            ?? throw new InvalidOperationException("WScript.Shell COM 不可用");
        object shell = Activator.CreateInstance(shellType)!;
        try
        {
            object link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path })!;
            try
            {
                string exe = Environment.ProcessPath ?? throw new InvalidOperationException("取 exe 路径失败");
                SetComProp(link, "TargetPath", exe);
                SetComProp(link, "Arguments", arguments);
                SetComProp(link, "WorkingDirectory", Path.GetDirectoryName(exe)!);
                SetComProp(link, "Description", description);
                SetComProp(link, "IconLocation", exe + ",0");
                link.GetType().InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
            }
            finally
            {
                Marshal.FinalReleaseComObject(link);
            }
        }
        finally
        {
            Marshal.FinalReleaseComObject(shell);
        }
    }

    private static void SetComProp(object target, string name, object value)
        => target.GetType().InvokeMember(name, BindingFlags.SetProperty, null, target, new[] { value });

    private void SaveConfig()    {
        var cfg = new AppConfig { Ratio = _ratio, Theme = AppTheme.Mode.ToString() };
        cfg.AttachedPids = new[] { _left, _right }
            .Where(c => c is not null)
            .Select(c => (long)c!.Pid)
            .ToList();
        cfg.AttachedHwnds = new[] { _left, _right }
            .Where(c => c is not null)
            .Select(c => c!.Hwnd.ToInt64())
            .ToList();
        // 几何持久化：正常态矩形（最大化/最小化关闭取 RestoreBounds）× 当前屏 DPI = 物理像素，
        // 加是否最大化——跨 DPI 启动不漂移，位置也一并恢复（恢复端钳到可见屏防幽灵窗）
        double scale = VisualTreeHelper.GetDpi(this).DpiScaleX;
        Rect normal = WindowState == WindowState.Normal
            ? new Rect(Left, Top, ActualWidth, ActualHeight)
            : RestoreBounds;
        cfg.WinLeft = normal.Left * scale;
        cfg.WinTop = normal.Top * scale;
        cfg.WinRight = normal.Right * scale;
        cfg.WinBottom = normal.Bottom * scale;
        cfg.WinMaximized = WindowState == WindowState.Maximized;
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
        // 保存几何落位：hwnd 已建，直接写物理像素（绕开 WPF 对 DIP 属性的初始主屏 DPI 解释）。
        // 两步：先移动（触发 WM_DPICHANGED、WPF 收敛到目标屏缩放），再设尺寸——WPF 跨 DPI
        // 保 DIP 不保物理，一次到位会被它按旧缩放改写
        if (_pendingPlacement is { } p)
        {
            _pendingPlacement = null;
            Native.SetWindowPos(_handle, IntPtr.Zero, (int)p.X, (int)p.Y, 0, 0,
                Native.SWP_NOSIZE | Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
            Native.SetWindowPos(_handle, IntPtr.Zero, 0, 0, (int)p.W, (int)p.H,
                Native.SWP_NOMOVE | Native.SWP_NOZORDER | Native.SWP_NOACTIVATE);
            if (p.Maximized) WindowState = WindowState.Maximized;
        }
        _lastOrigin = PointToScreen(new Point(0, 0));
        _drag = new DragAttach(this);
        _timer.Start();
        SetFallbackIcon();
        UpdateStatus(); // 首帧就显示空格占位提示（不等 250ms 维护定时器）
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
            child?.MoveBy(dx, dy);
        }
    }

    private void ApplyLayout()
    {
        if (_handle == IntPtr.Zero || !IsLoaded) return;
        ApplyLayoutTo(_left, AttachSide.Left);
        ApplyLayoutTo(_right, AttachSide.Right);
    }

    private bool ApplyLayoutTo(AttachedChild? child, AttachSide side)
    {
        if (child is null || !child.CanPlace) return false;
        if (ActualWidth < 50 || ActualHeight < 50) return false;

        var (x, y, w, h) = PaneRectDevice(side);

        // 外扩自身隐形边 + 插到宿主正下方，都在 child 内部完成
        return child.PlaceInPane(x, y, w, h);
    }

    private (int X, int Y, int W, int H) PaneRectDevice(AttachSide side)
    {
        double bw = CurBorderW;
        bool isLeft = side == AttachSide.Left;
        double availDip = Math.Max(0, ActualWidth - 2 * bw - _dividerW);
        double contentHDip = Math.Max(0, ActualHeight - 2 * bw - _topBarH);
        double leftWDip = availDip * _ratio;
        double xDip = isLeft ? bw : bw + leftWDip + _dividerW;
        double wDip = isLeft ? leftWDip : availDip - leftWDip;

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
            child?.PlaceBelowHost();
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
        if (!dragging && _highlight is not null) SetDragHighlight(null); // 拖动事件丢失时兜底熄灭高亮
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
                    child?.MoveOffscreen();
                }
                break;

            case WindowState.Maximized:
            case WindowState.Normal:
                // 最大化只改布局：吸附窗口随格子放大，不触发系统最大化；边框同步隐藏/恢复。
                // 立即按当前窗口宽校一次；WPF 尺寸回缩/边框变化完成后再校一次（Loaded 优先级），
                // 消除事件时序导致的分隔条位置漂移
                foreach (var child in new[] { _left, _right })
                {
                    child?.EnsureDockedState();
                }
                if (_outer is not null) _outer.BorderThickness = new Thickness(CurBorderW);
                UpdatePaneWidths();
                ApplyLayout();
                Dispatcher.BeginInvoke(() => { UpdatePaneWidths(); ApplyLayout(); }, DispatcherPriority.Loaded);
                break;
        }

        UpdateMaxGlyph();
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

    // IsAttachable / IsAttachedChild / IsDropAllowed / HitTestPaneAt / SetDragHighlight
    // 见 HostWindow.Attach.cs 与 HostWindow.Drag.cs

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
        // WM_GETICON/GetClassLong 返回的是子窗口自有的图标句柄（非副本），绝不能 DestroyIcon
        src.Freeze();
        return src;
    }

    /// <summary>任务栏大图标目标尺寸：PMv2 进程下随 DPI 缩放（32px@100% ↔ 48px@150%）。
    /// 固定 32px 画布在高 DPI 上比 shell 要的小一圈——HICON 按本征尺寸绘制、不放大。</summary>
    private (int W, int H) TaskbarIconSize()
    {
        int w = Native.GetSystemMetrics(Native.SM_CXICON);
        int h = Native.GetSystemMetrics(Native.SM_CYICON);
        return (w > 0 ? w : 32, h > 0 ? h : 32);
    }

    /// <summary>把图标源拉伸绘制到任务栏尺寸画布（小源放大保持可见面积，shell 不再缩水）。</summary>
    private BitmapSource OnTaskbarCanvas(BitmapSource src)
    {
        var (w, h) = TaskbarIconSize();
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            dc.DrawImage(src, new Rect(0, 0, w, h));
        }
        var rtb = new RenderTargetBitmap(w, h, 96, 96, PixelFormats.Pbgra32);
        rtb.Render(visual);
        rtb.Freeze();
        return rtb;
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

        // 两枚图标对角叠放：右窗右上（先画在下），左窗左下（后画盖在上面）；
        // 单侧吸附时空位叠本程序图标占位——一眼能看出还有一格空着。
        // 画布随任务栏 DPI（比例：子图标 3/4、偏移 1/4）
        BitmapSource? app = LoadAppIconFrame();
        if (app is null)
        {
            Icon = OnTaskbarCanvas(l ?? r!); // 应用图标资源损坏时退化到现有源
            return;
        }
        var topRight = r ?? app;
        var bottomLeft = l ?? app;
        var (w, h) = TaskbarIconSize();
        double cell = Math.Min(w, h);
        double iconSize = cell * 3 / 4;
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            dc.DrawImage(topRight, new Rect(cell / 4, 0, iconSize, iconSize));
            dc.DrawImage(bottomLeft, new Rect(0, cell / 4, iconSize, iconSize));
        }
        var rtb = new RenderTargetBitmap(w, h, 96, 96, PixelFormats.Pbgra32);
        rtb.Render(visual);
        rtb.Freeze();
        Icon = rtb;
    }

    // 吸附编排（TryAttach/Release*/SwapSides/Pick 及 CLI 匹配）见 HostWindow.Attach.cs
    // 拖拽交互（顶条拖动/最大化拖动还原/分隔条拖动）见 HostWindow.Drag.cs

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
        UpdatePaneHints();
    }

    /// <summary>空格显示填充与提示文案（不再透明穿透）；该侧吸附后隐藏占位恢复透明——
    /// 子窗口要靠透明格子透出、点击穿透下去交互，吸附格必须回到透明。</summary>
    private void UpdatePaneHints()
    {
        _leftHint.Visibility = _left is null ? Visibility.Visible : Visibility.Collapsed;
        _rightHint.Visibility = _right is null ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ShowNotice(string text)
    {
        _notice = text;
        _noticeUntil = DateTime.UtcNow + TimeSpan.FromSeconds(3);
        UpdateStatus();
    }

    private static bool IsCtrlHeld()
        => Keyboard.IsKeyDown(Key.LeftCtrl) || Keyboard.IsKeyDown(Key.RightCtrl);

    /// <summary>左右按钮随格子占用状态翻转：空格=吸附选择（左←/右→），已吸附=释放该侧（f2d2）。</summary>
    private void UpdateSideButtons()
    {
        var sides = new[]
        {
            (Button: _pickLeftButton, Child: ChildAt(AttachSide.Left), EmptyGlyph: "\uF060",
             PickTip: "选择左窗…", ReleaseTip: "释放左窗（回到原位）"),
            (Button: _pickRightButton, Child: ChildAt(AttachSide.Right), EmptyGlyph: "\uF061",
             PickTip: "选择右窗…", ReleaseTip: "释放右窗（回到原位）"),
        };
        foreach (var (btn, child, emptyGlyph, pickTip, releaseTip) in sides)
        {
            bool used = child is not null;
            btn.Content = used ? "\uF2D2" : emptyGlyph;
            btn.ToolTip = used ? releaseTip : pickTip;
        }
    }

    /// <summary>释放指定侧的吸附窗口（回原位、恢复任务栏与圆角）。</summary>
    private void ReleaseSide(AttachSide side)
    {
        ChildAt(side)?.Restore();
        if (side == AttachSide.Left) _left = null; else _right = null;
        UpdateStatus();
        UpdateHostIcon();
    }

    private static string PaneTitle(IntPtr hwnd)
        => hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) ? "空" : Truncate(Native.GetTitle(hwnd), 40);

    private static string Truncate(string s, int max)
        => s.Length <= max ? s : s[..(max - 1)] + "…";
}
