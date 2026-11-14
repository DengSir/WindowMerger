using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
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
    private bool _barHidden;                        // 最大化自动隐藏：顶条当前收起？
    private readonly DispatcherTimer _revealTimer;  // 最大化顶条移入显隐轮询（100ms）

    private const double MinRatio = 0.2;
    private const double MaxRatio = 0.8;

    private const int WM_NCHITTEST = 0x0084;
    private const int WM_GETMINMAXINFO = 0x0024;
    private const int WM_SETTINGCHANGE = 0x001A;
    private const int HTCLIENT = 1;

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

    // 自动更新（逻辑在 Updater.cs，这里只做状态机与 UI）
    private bool _checkUpdates;                 // 启动自动检查开关（config.CheckUpdates，主题菜单可切）
    private Updater.UpdateInfo? _update;        // 发现的可用更新（null=无）
    private string? _updateZip;                 // 已下载的更新包路径（null=未下载）
    private UpdatePhase _updatePhase = UpdatePhase.Idle;
    private bool _pendingInstall;               // 重启安装已确认：Closing 清理完成后换 exe

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

    public HostWindow(AppConfig config, StartupOptions? opts = null)
    {
        if (Enum.TryParse<AppThemeMode>(config.Theme, true, out var mode)) AppTheme.Mode = mode;
        _ratio = Math.Clamp(config.Ratio, MinRatio, MaxRatio);
        _checkUpdates = config.CheckUpdates;
        var orphanPids = config.AttachedPids;
        var orphanHwnds = config.AttachedHwnds;

        InitializeComponent();

        if (opts?.Snap is { } snap)
        {
            // snap 接管落位：两窗口可见边界并集（物理 px，现场实测非陈旧保存值）——跳过
            // config 几何恢复（接管几何由当前布局决定，不是用户偏好），只钳最小尺寸防极端；
            // 比例 = 左窗宽占比（与工作区分界的偏差 ≈ 边框 2 DIP，可忽略）。
            // 直接最大化：检测要求并集 ≈ 目标屏工作区（±8px），最大化矩形即工作区——
            // 顶条 overlay 自动隐藏（触顶唤出）随之生效，子窗占满全高
            double scale = Native.MonitorDpiScale(Native.MonitorFromPoint(
                new Native.POINT { X = (int)(snap.Rect.X + snap.Rect.W / 2), Y = (int)(snap.Rect.Y + snap.Rect.H / 2) },
                Native.MONITOR_DEFAULTTONEAREST));
            _pendingPlacement = (snap.Rect.X, snap.Rect.Y,
                Math.Max(snap.Rect.W, MinWidth * scale), Math.Max(snap.Rect.H, MinHeight * scale), true);
            _ratio = Math.Clamp(snap.Ratio, MinRatio, MaxRatio);
        }
        else
        {
            // 几何恢复（Windows 原生惯例）：正常态矩形（物理像素）+ 是否最大化，校验钳制到
            // 可见显示器工作区后暂存，hwnd 建好后 OnSourceInitialized 落位——显示器断开/
            // 分辨率变化/配置损坏都不能产生屏外幽灵窗。无有效几何默认 960×600 主屏居中
            _pendingPlacement = ResolvePlacement(config);
        }
        Width = 960;
        Height = 600;
        // hwnd 建好前的初始值（无有效几何时即最终状态）；有保存几何时 OnSourceInitialized
        // 用 SetWindowPos 写物理像素落位，绕开 WPF 对 DIP 属性的初始主屏 DPI 解释

        WireUi();
        ApplyTheme(); // XAML 只带深色初值，按配置主题重刷一遍（含按钮前景）

        // 顶条叠层：非最大化顶条占位（上边距=顶条高，视觉同旧 DockPanel 行）；
        // 最大化走自动隐藏浮层，ApplyTopBarMode 随状态切换
        _content.Margin = new Thickness(0, _topBarH, 0, 0);
        _revealTimer = new DispatcherTimer(DispatcherPriority.Input)
        {
            Interval = TimeSpan.FromMilliseconds(100),
        };
        _revealTimer.Tick += (_, _) => PollTopBarReveal();

        LocationChanged += (_, _) => OnHostMoved();
        SizeChanged += (_, _) => { UpdatePaneWidths(); ApplyLayout(); };
        StateChanged += (_, _) => OnStateChanged();
        Activated += (_, _) =>
        {
            EnsureChildDocked(AttachSide.Left);
            EnsureChildDocked(AttachSide.Right);
            RaiseChildrenBelow();
            // 宿主激活把宿主单独升到 z 序顶端，子窗口留在原地；低优先级再插回一次加固
            Dispatcher.BeginInvoke(RaiseChildrenBelow, DispatcherPriority.Background);
        };
        DpiChanged += (_, _) => ApplyLayout();
        Loaded += (_, _) => { UpdatePaneWidths(); ApplyLayout(); CleanupOrphanedChildren(orphanPids, orphanHwnds); AttachStartupTargets(opts); };
        Closing += OnClosing;

        _timer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(250),
        };
        _timer.Tick += (_, _) => Maintain();

        // 上次更新的残留（.old/.update/临时 zip）：新实例启动即清；.old 可能仍被退出中的
        // 旧进程占用，删不掉定时重试自愈
        CleanupUpdateLeftoversWithRetry();

        // 启动自动检查更新：延迟 4 秒避开启动高峰，失败静默（离线/代理未就绪不打扰）。
        // WM_UPDATE_OFF=1（wm.py 导入即注入 + run_all/CI）：测试宿主与真实 GitHub API
        // 彻底断网——发现新版本会自动弹模态确认框（抢焦点 + 禁用宿主 UI），测试环境
        // 必须不检查；update_e2e 剥掉本变量测真实流程，用 WM_UPDATE_API 指本地假服务
        if (Environment.GetEnvironmentVariable("WM_UPDATE_OFF") != "1")
        {
            var updateCheckTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(4) };
            updateCheckTimer.Tick += (_, _) =>
            {
                updateCheckTimer.Stop();
                if (_checkUpdates) AutoCheckUpdate();
            };
            updateCheckTimer.Start();
        }
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
        // 顶条「全部释放」：用户主动释放 → 两窗置顶回原位并激活右窗。前台只能转交
        // 一次（首次 SetForegroundWindow 已交出宿主的前台，第二次被前台锁拒绝），
        // 所以置顶走无激活 z 序、激活只做一次；ReleaseAll 本体保持纯净——宿主关闭
        // 清理路径复用它，不拉前台
        _releaseButton.Click += (_, _) =>
        {
            var l = _left?.Hwnd ?? IntPtr.Zero;
            var r = _right?.Hwnd ?? IntPtr.Zero;
            ReleaseAll();
            RaiseReleasedWindow(l);
            RaiseReleasedWindow(r);
            Native.SetForegroundWindow(r != IntPtr.Zero ? r : l);
        };
        _shortcutButton.Click += (_, _) => CreateShortcutForCurrent();
        _themeButton.Content = ThemeGlyph();
        _themeButton.Click += (_, _) => OpenThemeMenu();
        _minimizeButton.Click += (_, _) => WindowState = WindowState.Minimized;
        _maxButton.Click += (_, _) => ToggleMaximize();
        _closeButton.Click += (_, _) => Close();
        UpdateMaxGlyph(); // 初始字形（CaptionIcons 原版 ChromeMaximize，XAML 同款）

        _updateButton.Click += (_, _) => _ = OnUpdateButtonClickedAsync();
        SetUpdatePhase(UpdatePhase.Idle); // 初始字形/tooltip（含当前版本号）

        _topBar.MouseLeftButtonDown += TopBarOnMouseDown;
        _topBarFrame.MouseLeftButtonDown += TopBarOnMouseDown; // 浮层态四边框带也归顶条交互
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
        menu.Items.Add(new Separator());
        menu.Items.Add(MenuItemWithCheck("启动时检查更新", _checkUpdates, p,
            () => { _checkUpdates = !_checkUpdates; SaveConfig(); }, "ToggleCheckUpdates"));
        menu.IsOpen = true;
    }

    private MenuItem ThemeMenuItem(string label, AppThemeMode mode, AppTheme.Palette p)
        => MenuItemWithCheck(label, AppTheme.Mode == mode, p, () =>
        {
            AppTheme.Mode = mode;
            ApplyTheme();
            SaveConfig();
        });

    /// <summary>主题菜单通用项（主题三选 + 启动检查更新开关共用）：极简模板 + 对勾列 + 悬停高亮。
    /// 自定义 Header 的 MenuItem UIA Name 为空（AGENTS 已知坑），可传 automationId 供测试定位。</summary>
    private MenuItem MenuItemWithCheck(string label, bool checkmark, AppTheme.Palette p, Action onClick,
        string? automationId = null)
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
            Text = checkmark ? "\uF00C" : "",
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
        if (automationId is not null)
            item.SetValue(System.Windows.Automation.AutomationProperties.AutomationIdProperty, automationId);
        item.MouseEnter += (_, _) => item.Background = AppTheme.Brush(AppTheme.Current().ButtonHover);
        item.MouseLeave += (_, _) => item.Background = Brushes.Transparent;
        item.Click += (_, _) => onClick();
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
        var cfg = new AppConfig { Ratio = _ratio, Theme = AppTheme.Mode.ToString(), CheckUpdates = _checkUpdates };
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
        // CaptionIcons（Segoe Fluent Icons，XAML）只切换字形：E922 最大化方块 ↔ E923
        // 原版还原（Windows 标题栏自渲染字形，天生朝向正确——替代旧 FA f24d+旋转方案）
        _maxButton.Content = WindowState == WindowState.Maximized ? "\uE923" : "\uE922";
    }

    private void ToggleMaximize()
        => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    // ---------- 生命周期 ----------

    /// <summary>时序打点（WM_TRACE=1 才写 %TEMP%\wm_trace.log）：验证 SourceInitialized →
    /// Loaded → 吸附 → 拼图 的真实顺序用，模态 MessageBox 会泵 dispatcher 扭曲时序不能用。</summary>
    private static void TracePoint(string msg)
    {
        if (Environment.GetEnvironmentVariable("WM_TRACE") != "1") return;
        try
        {
            File.AppendAllText(Path.Combine(Path.GetTempPath(), "wm_trace.log"),
                $"{DateTime.Now:HH:mm:ss.fff} {msg}\n");
        }
        catch
        {
            // trace 只是诊断，失败忽略
        }
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        TracePoint("OnSourceInitialized enter");
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
        UpdateHostIcon(); // 初始即走统一图标管线（此刻 _left/_right 必空 → 内部落 SetFallbackIcon）
        UpdateStatus(); // 首帧就显示空格占位提示（不等 250ms 维护定时器）
        TracePoint("OnSourceInitialized exit");
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
    /// 吸附后由 UpdateHostIcon 换成双子窗口合成图标（OnSourceInitialized 起统一走 UpdateHostIcon）。
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
        if (msg == WM_NCHITTEST && WindowState == WindowState.Maximized)
        {
            // WindowChrome 的 resize 边命中测试不区分最大化状态（WPF _HitTestNca 无该检查）：
            // 最大化时窗口顶边=屏幕顶边，顶条最上 8 DIP 被判成 HTTOP 缩放区——鼠标按在
            // 屏幕顶上拖不动（实测，回归 tools/tests/max_top_drag_test.py），四边同理。
            // 最大化本就不可缩放（Windows 标准行为），整窗一律 HTCLIENT，
            // 顶条拖动还原走 TopBarOnMouseDown 自己的鼠标事件逻辑。
            handled = true;
            return (IntPtr)HTCLIENT;
        }
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

    /// <summary>关闭收尾 + 重启安装：先还原子窗口/落盘配置（AttachedPids 随之清空，新实例
    /// 不会误吸附），再换 exe 拉起新实例——此刻本进程已无窗口级状态可丢。换装任何一步失败
    /// 都取消关闭（窗口留着）并报因，用户可重试或正常继续使用。</summary>
    private void OnClosing(object? sender, CancelEventArgs e)
    {
        OnClosingCleanup();
        if (!_pendingInstall) return;
        try
        {
            Updater.InstallAndRestart(_updateZip!);
        }
        catch (Exception ex)
        {
            e.Cancel = true;
            _pendingInstall = false;
            ShowNotice($"安装更新失败：{ex.Message}");
        }
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
        double contentHDip = Math.Max(0, ActualHeight - 2 * bw - TopInset);
        double leftWDip = availDip * _ratio;
        double xDip = isLeft ? bw : bw + leftWDip + _dividerW;
        double wDip = isLeft ? leftWDip : availDip - leftWDip;

        var tl = PointToScreen(new Point(xDip, bw + TopInset));
        var br = PointToScreen(new Point(xDip + wDip, bw + TopInset + contentHDip));
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

    /// <summary>
    /// 子窗口激活联动：把整个合并单元升到所有普通窗口之上，焦点保持在子窗口。
    /// 点击格子（alpha=0 穿透）激活的是子窗口，系统只升子窗口不升宿主——重叠的
    /// 其他窗口继续压住单元，观感是"点了没反应，子窗口还被拽回去"。宿主用
    /// topmost-toggle 两步落到普通带顶端再 RaiseChildrenBelow 粘回子窗口；
    /// 全程 NOACTIVATE 绝不抢焦点（SetForegroundWindow 会打断子窗口输入），
    /// HWND_TOP 对非前台窗口实测静默无效不可用。最小化/拖动中跳过。
    /// </summary>
    internal void OnChildActivated(IntPtr child)
    {
        if (_handle == IntPtr.Zero || !IsLoaded || WindowState == WindowState.Minimized) return;
        if (_drag is { IsBusy: true }) return;
        // topmost-toggle：第二步只在第一步成功后执行（NOTOPMOST 落普通带顶端）
        if (Native.SetWindowPos(_handle, Native.HwndTopmost, 0, 0, 0, 0,
                Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE
                | Native.SWP_NOOWNERZORDER))
            Native.SetWindowPos(_handle, Native.HwndNotTopmost, 0, 0, 0, 0,
                Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE
                | Native.SWP_NOOWNERZORDER);
        RaiseChildrenBelow();
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
        // 宿主正下方必须是连续的"可见子窗口块"（次序不限）：Alt+Tab 切回时宿主单独升顶，
        // 子窗口留在原地会被切走前的前台窗口压住（宿主内 HWND_TOP 拉起实测无效），不满足
        // 就整体插回宿主正下方。最小化（移出屏幕外但非 iconic）的子窗口豁免。
        // 跳过隐藏/cloaked 窗口：它们不渲染、不参与命中，为它们翻转子窗口 z 纯属浪费，
        // 且每次写入都是一次 DWM 重合成（闪烁）——与 IsCoveredAtCursor 同一判定标准。
        IntPtr b1 = _handle == IntPtr.Zero ? IntPtr.Zero : Native.GetWindow(_handle, Native.GW_HWNDNEXT);
        IntPtr below = b1;
        bool leftOk = false, rightOk = false;
        for (int seen = 0, hops = 0; seen < 2 && below != IntPtr.Zero && hops < 32; hops++)
        {
            if (!Native.IsWindowVisible(below) || Native.IsCloaked(below))
            {
                below = Native.GetWindow(below, Native.GW_HWNDNEXT);
                continue;
            }
            if (_left is not null && below == _left.Hwnd) leftOk = true;
            if (_right is not null && below == _right.Hwnd) rightOk = true;
            seen++;
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

        // 吸附态外观自愈：任务栏隐藏标记可能被 shell 侧重新收录（无查询接口，见
        // EnsureDockedState 的低频重断言）；吸附子窗口没有任务栏按钮，最小化后无从手动
        // 还原；独立最大化则摧毁合并布局——宿主可见期间一律拉回格子自愈（子窗口自身
        // 没有"最大化"概念）。例外：应用自行隐藏（关闭/最小化到托盘类）→ 上报后走
        // 释放还原，不拉回（见 ReleaseHiddenSide）
        EnsureChildDocked(AttachSide.Left);
        EnsureChildDocked(AttachSide.Right);

        UpdatePaneWidths(); // 分隔条视觉位置与 _ratio 的持续对账（自愈任何布局漂移）
        ApplyLayout();
        FixZOrder();
    }

    // ---------- 状态联动 ----------

    private void OnStateChanged()
    {
        ApplyTopBarMode(); // 最大化 ↔ 其他：顶条浮层占位/自动隐藏与轮询启停
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
                EnsureChildDocked(AttachSide.Left);
                EnsureChildDocked(AttachSide.Right);
                if (_outer is not null) _outer.BorderThickness = new Thickness(CurBorderW);
                UpdatePaneWidths();
                ApplyLayout();
                Dispatcher.BeginInvoke(() => { UpdatePaneWidths(); ApplyLayout(); }, DispatcherPriority.Loaded);
                break;
        }

        UpdateMaxGlyph();
    }

    // ---------- 最大化顶条自动隐藏（触顶唤出、移出隐藏） ----------

    private bool BarOverlayMode => WindowState == WindowState.Maximized;

    /// <summary>几何公式的顶内缩：最大化时顶条变浮层不占布局，子窗占满全高——
    /// 顶条移入显示时盖在子窗口上方（宿主渲染天然在子窗 hwnd 之上）。</summary>
    private double TopInset => BarOverlayMode ? 0 : _topBarH;

    /// <summary>最大化 ↔ 其他的顶条模式切换：占位边距、显隐状态与轮询启停。</summary>
    private void ApplyTopBarMode()
    {
        bool overlay = BarOverlayMode;
        _content.Margin = overlay ? default : new Thickness(0, _topBarH, 0, 0);
        // 浮层态画四边 2 DIP 全框（=正常态外框的同色同宽翻版，观感一致：框跟着顶条浮起来）；
        // 正常态不画——外框已经包着顶条，再画会叠双线。框画在 _topBarFrame（_topBar 外面），
        // _topBar.Height 恒 28 不动：底色带视觉高度与正常态一致，边框不侵占顶条本体
        const double barFrame = 2;
        _topBarFrame.BorderThickness = overlay ? new Thickness(barFrame) : default;
        if (overlay)
        {
            // 点最大化按钮时鼠标就在带内 → 先显示。此刻 _barHidden 恒 false
            // （离开最大化必经 SetBarShown(true)）→ 走整条带判定，顶条不会在
            // 光标底下当场消失；之后的收起交给轮询（移出顶条 / 触顶再唤出）
            SetBarShown(CursorInTopStrip());
            _revealTimer.Start();
        }
        else
        {
            _revealTimer.Stop();
            SetBarShown(true);
        }
    }

    // 触顶唤出阈值带（DIP，issue #1）：隐藏态只有光标贴住窗口最上沿才滑入顶条，
    // 整条顶条高度都触发会盖住顶部内容；显示态沿用同值作底边迟滞带
    private const double TopTouchBand = 6;

    private bool CursorInTopStrip()
    {
        if (!Native.GetCursorPos(out var p)) return false;
        var w = PointFromScreen(new Point(p.X, p.Y)); // 物理像素 → 窗口 DIP
        // 触顶唤出、移出隐藏（issue #1，Windows 自动隐藏任务栏语义）：隐藏态只在
        // 触顶阈值带内才滑入；已显示时停留区 = 顶条全高 + 迟滞带——光标停在底边
        // 附近不因 ±1px 抖动闪烁，移出顶条才收起
        double band = _barHidden ? TopTouchBand : _topBarFrame.ActualHeight + TopTouchBand;
        return w.Y <= band && w.X >= -8 && w.X <= ActualWidth + 8;
    }

    private void PollTopBarReveal()
    {
        if (!BarOverlayMode)
        {
            _revealTimer.Stop();
            return;
        }
        // 最大化拖还原全程捕获顶条：拖动中光标会离开顶条带，收起会掐断拖拽
        if (_topBar.IsMouseCaptured || _maxDragActive)
        {
            SetBarShown(true);
            return;
        }
        SetBarShown(CursorInTopStrip());
    }

    private void SetBarShown(bool show)
    {
        if (_barHidden == !show) return;
        _barHidden = !show;
        var to = show ? 0d : -_topBarFrame.ActualHeight - 2; // 平移出窗口表面即不可见（hwnd 表面裁剪）
        _barSlide.BeginAnimation(TranslateTransform.YProperty,
            new DoubleAnimation(_barSlide.Y, to, TimeSpan.FromMilliseconds(120)));
    }

    /// <summary>
    /// 启动时清理上一会话的孤儿：宿主被强杀时已吸附子窗口会残留吸附态外观
    /// （任务栏/Alt+Tab 被删、圆角直角化、可能停在屏幕外），按记录的 HWND 精确还原。
    /// 不能按 PID 枚举：进程的隐藏辅助窗口（CiceroUIWndFrame 等）会被误显示成
    /// "点不出来的任务栏幽灵按钮"（实测踩坑）。PID 仅用于句柄复用校验。
    /// </summary>
    private static void CleanupOrphanedChildren(List<long>? pids, List<long>? hwnds)
    {
        if (hwnds is not { Count: > 0 } || pids is not { Count: > 0 }) return;
        var pidSet = pids.ToHashSet();
        foreach (var raw in hwnds)
        {
            var h = new IntPtr(raw);
            if (!Native.IsWindow(h)) continue;
            Native.GetWindowThreadProcessId(h, out uint pid);
            if (!pidSet.Contains(pid)) continue; // 句柄已被复用给其他进程，跳过
            Native.SetTaskbarTab(h, show: true); // 任务栏重新收录（已收录时是幂等 no-op）
            Native.SetSquareCorners(h, square: false); // 圆角还原（强杀时 Undock 没跑）
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
        bool shellCopy = false;
        if (hIcon == IntPtr.Zero)
        {
            // UWP/框架窗兜底（snap 接管实测：设置等 ApplicationFrameWindow 四连全 miss——
            // 其任务栏图标走 app tile，窗口本身无素材）：按进程 exe 取 shell 图标；
            // 框架窗的外框进程是 ApplicationFrameHost（通用窗图标），经子 CoreWindow
            // 找真实应用进程（SystemSettings 等，exe 图标即应用图标）
            hIcon = GetShellIconForWindow(hwnd);
            shellCopy = hIcon != IntPtr.Zero;
        }
        if (hIcon == IntPtr.Zero) return null;

        var src = Imaging.CreateBitmapSourceFromHIcon(hIcon, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
        if (shellCopy)
        {
            Native.DestroyIcon(hIcon); // SHGetFileInfo 返回的是副本，用完销毁；
        }
        // WM_GETICON/GetClassLong 返回的是子窗口自有的图标句柄（非副本），绝不能 DestroyIcon
        src.Freeze();
        return src;
    }

    /// <summary>按窗口所属进程 exe 取 shell 图标（ApplicationFrameWindow 走子 CoreWindow 进程）。
    /// 返回的 HICON 是 shell 分配的副本，调用方必须 DestroyIcon。</summary>
    private IntPtr GetShellIconForWindow(IntPtr hwnd)
    {
        Native.GetWindowThreadProcessId(hwnd, out uint pid);
        string path = Native.GetProcessImagePath(pid) ?? "";
        if (Native.GetClassNameOf(hwnd) == "ApplicationFrameWindow")
        {
            IntPtr core = Native.FindWindowEx(hwnd, IntPtr.Zero, "Windows.UI.Core.CoreWindow", null);
            if (core != IntPtr.Zero)
            {
                Native.GetWindowThreadProcessId(core, out uint corePid);
                string corePath = Native.GetProcessImagePath(corePid) ?? "";
                if (corePath.Length > 0) path = corePath;
            }
        }
        if (path.Length == 0) return IntPtr.Zero;
        var shfi = new Native.SHFILEINFOW();
        if (Native.SHGetFileInfoW(path, Native.FILE_ATTRIBUTE_NORMAL, ref shfi,
                (uint)Marshal.SizeOf<Native.SHFILEINFOW>(), Native.SHGFI_ICON | Native.SHGFI_LARGEICON)
            != IntPtr.Zero)
        {
            return shfi.hIcon;
        }
        return IntPtr.Zero;
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
        TracePoint($"UpdateHostIcon: left={(l != null ? "素材" : "无")} right={(r != null ? "素材" : "无")} " +
                   $"({_left?.Hwnd.ToInt64() ?? 0}/{_right?.Hwnd.ToInt64() ?? 0})");
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

    // ---------- 自动更新（网络/换装逻辑在 Updater.cs） ----------

    private enum UpdatePhase { Idle, Checking, Available, Downloading }

    /// <summary>更新组状态：无更新/检查失败（Idle/Checking）时按钮+文案整体隐藏不占顶条，
    /// 启动自动检查发现新版本才现身「发现新版本 ⬇」（功能区最左）→ 自动弹确认框
    /// （UpdateDialog）→ 下载（状态栏进度）→ 自动重启安装；点 ⬇ 直接下载不再询问。
    /// 只动 Visibility/Content/ToolTip/IsEnabled——不碰 DynamicResource 引用（悬停刷色由
    /// 隐式样式 Trigger 管）。AutomationProperties.Name 跟随状态：e2e 的状态探针 + 读屏可读。</summary>
    private void SetUpdatePhase(UpdatePhase phase)
    {
        _updatePhase = phase;
        string version = _update?.Version ?? "?";
        bool enabled;
        bool visible;
        string glyph;
        string label;
        switch (phase)
        {
            case UpdatePhase.Checking:
                enabled = false; visible = false; glyph = "\uF021"; label = "正在检查更新…";
                break;
            case UpdatePhase.Available:
                enabled = true; visible = true; glyph = "\uF019"; // 下载
                label = _updateZip is not null
                    ? $"已下载 {version}，点击安装"
                    : $"发现新版本 {version}，点击下载安装";
                break;
            case UpdatePhase.Downloading:
                enabled = false; visible = true; glyph = "\uF019"; label = "下载更新中…";
                break;
            default: // Idle：无更新不显示图标
                enabled = true; visible = false; glyph = "\uF021";
                label = $"检查更新（当前 {Updater.CurrentDisplayVersion()}）";
                break;
        }
        _updateButton.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
        _updateLabel.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
        _updateButton.IsEnabled = enabled;
        _updateButton.Content = glyph;
        _updateButton.ToolTip = label;
        _updateLabel.ToolTip = label;
        // 普通依赖属性动态赋值，与主题资源（DynamicResource）无关，无资源引用销毁陷阱
        _updateButton.SetValue(System.Windows.Automation.AutomationProperties.NameProperty, label);
    }

    /// <summary>更新按钮点击（只在 Available 态可见可点）：直接下载安装——确认框在检查
    /// 发现新版本时已自动弹过，这里不再二次询问，也不重新检查版本。</summary>
    private async Task OnUpdateButtonClickedAsync()
    {
        if (_updatePhase == UpdatePhase.Available && _update is { } info)
        {
            await DownloadAndInstallAsync(info, cached: _updateZip is not null && File.Exists(_updateZip));
        }
    }

    /// <summary>启动唯一一次检查 GitHub 最新 Release：发现新版本 → Available（顶条现身
    /// 「发现新版本 ⬇」）并直接弹确认框——一次性宣告，确认或点 ⬇ 都直接下载安装，
    /// 取消后顶条按钮随时可再点。无更新/失败静默——更新组保持隐藏（离线、代理未就绪
    /// 不打扰）。检查异常由 AutoCheckUpdate 吞掉。</summary>
    private async Task CheckUpdateAsync()
    {
        SetUpdatePhase(UpdatePhase.Checking);
        var check = await Updater.CheckLatestAsync();
        if (check.Update is { } info)
        {
            _update = info;
            SetUpdatePhase(UpdatePhase.Available);
            await PromptUpdateAsync();
        }
        else
        {
            _update = null;
            SetUpdatePhase(UpdatePhase.Idle);
        }
    }

    /// <summary>发现新版本后的确认对话框。确认 → 直接下载安装；取消 → 留在 Available
    /// （顶条 ⬇ 随时可点，点了直接下载不再询问）。下载/安装失败在 DownloadAndInstallAsync
    /// 报因——自动检查路径已过用户确认，必须可见。</summary>
    private async Task PromptUpdateAsync()
    {
        if (_update is not { } info) return;
        bool cached = _updateZip is not null && File.Exists(_updateZip);
        var dlg = new UpdateDialog(
            headline: $"发现新版本 {info.Version}",
            detail: cached
                ? $"更新包已下载（当前 {Updater.CurrentDisplayVersion()}），重启即自动完成替换。"
                : $"当前版本 {Updater.CurrentDisplayVersion()}。将下载更新包并自动重启安装，吸附的子窗口会先回到原位。",
            confirmText: cached ? "立即重启" : "立即更新")
        {
            Owner = this,
        };
        if (dlg.ShowDialog() != true)
        {
            ShowNotice("已取消更新，点顶条更新按钮可随时安装");
            return;
        }
        await DownloadAndInstallAsync(info, cached);
    }

    /// <summary>下载（更新包已缓存则跳过）→ 自动重启换装。用户已明确意向（确认框或点
    /// ⬇），失败不上抛崩宿主：状态回退 + 状态栏报因，已下载的包不丢（Available 档
    /// tooltip 会反映"已下载"）。</summary>
    private async Task DownloadAndInstallAsync(Updater.UpdateInfo info, bool cached)
    {
        try
        {
            if (!cached)
            {
                SetUpdatePhase(UpdatePhase.Downloading);
                using var cts = new CancellationTokenSource(TimeSpan.FromMinutes(3));
                _updateZip = await Updater.DownloadAsync(info, ShowNotice, cts.Token);
            }
            ShowNotice(cached ? "正在重启安装…" : "下载完成，正在重启安装…");
            InstallUpdate();
        }
        catch (Exception ex)
        {
            SetUpdatePhase(_update is not null ? UpdatePhase.Available : UpdatePhase.Idle);
            ShowNotice($"更新失败：{ex.Message}");
        }
    }

    /// <summary>启动静默检查的守卫：状态离开 Idle 就不查（保险，当前只有 4s 定时器一个
    /// 触发源）；检查失败完全静默，更新组保持隐藏。确认框/下载/安装的失败已在
    /// DownloadAndInstallAsync 报因，这里不再兜底。</summary>
    private async void AutoCheckUpdate()
    {
        try
        {
            if (_updatePhase != UpdatePhase.Idle) return;
            await CheckUpdateAsync();
        }
        catch
        {
            // 检查失败静默（网络异常等）
        }
    }

    /// <summary>重启安装：只标记 _pendingInstall 后正常 Close——真正换装在 Closing 里
    /// 子窗口还原、配置落盘之后执行（失败会取消关闭、状态不丢）。</summary>
    private void InstallUpdate()
    {
        if (_updateZip is null || !File.Exists(_updateZip))
        {
            _updateZip = null;
            SetUpdatePhase(_update is null ? UpdatePhase.Idle : UpdatePhase.Available);
            ShowNotice("更新包丢失，请重新下载");
            return;
        }
        _pendingInstall = true;
        Close();
    }

    /// <summary>清理上次更新的残留（.old/.update/临时 zip）。.old 可能仍被退出中的旧进程
    /// 占用（改名的镜像在跑），1.5s × 4 次重试自愈。</summary>
    private void CleanupUpdateLeftoversWithRetry()
    {
        if (Updater.CleanupLeftovers()) return;
        var retry = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        int attempts = 0;
        retry.Tick += (_, _) =>
        {
            if (Updater.CleanupLeftovers() || ++attempts >= 4) retry.Stop();
        };
        retry.Start();
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

    /// <summary>左右按钮随格子占用状态翻转：空格=吸附选择（左←/右→），已吸附=释放该侧
    /// （f08b 退出括号：左侧 ScaleX 镜像成 ←]、右侧原向 [→——FA 无原生镜像字形，实测扫描）。</summary>
    private void UpdateSideButtons()
    {
        var sides = new[]
        {
            (Button: _pickLeftButton, Child: ChildAt(AttachSide.Left), EmptyGlyph: "\uF060",
             PickTip: "选择左窗…", ReleaseTip: "释放左窗（回到原位）", Mirror: true),
            (Button: _pickRightButton, Child: ChildAt(AttachSide.Right), EmptyGlyph: "\uF061",
             PickTip: "选择右窗…", ReleaseTip: "释放右窗（回到原位）", Mirror: false),
        };
        foreach (var (btn, child, emptyGlyph, pickTip, releaseTip, mirror) in sides)
        {
            bool used = child is not null;
            // Content 保持字符串：UIA Name 跟随字形，topbar_state_test 按它断言翻转
            btn.Content = used ? "\uF08B" : emptyGlyph;
            btn.RenderTransform = used && mirror ? new ScaleTransform(-1, 1) : null;
            btn.ToolTip = used ? releaseTip : pickTip;
        }
    }

    /// <summary>用户主动释放指定侧的吸附窗口（回原位、恢复任务栏与圆角）并拉回前台：
    /// Restore 按 NOZORDER+NOACTIVATE 放回普通层，窗口常埋在其他窗口后面，用户点
    /// 释放就是想接着用它。仅侧按钮路径调用；替换/关闭清理等非主动释放不拉前台。</summary>
    private void ReleaseSide(AttachSide side)
    {
        var child = ChildAt(side);
        if (child is null) return;
        var hwnd = child.Hwnd;
        child.Restore();
        if (side == AttachSide.Left) _left = null; else _right = null;
        RaiseReleasedWindow(hwnd);
        Native.SetForegroundWindow(hwnd); // 单侧释放只有一次前台转交，必然在授权内
        UpdateStatus();
        UpdateHostIcon();
    }

    /// <summary>释放后把窗口置顶（无激活）：Restore 把窗口放回普通层且不带 z 序写入，
    /// 窗口常埋在其他窗口后面，先保证可见。z 序重排不受前台锁限制（受限的是激活）。</summary>
    private static void RaiseReleasedWindow(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || !Native.IsWindow(hwnd)) return;
        Native.SetWindowPos(hwnd, Native.HwndTop, 0, 0, 0, 0,
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE
            | Native.SWP_NOOWNERZORDER);
    }

    /// <summary>单侧吸附态自愈入口：应用自行隐藏（连续两个维护周期不可见）→ 走释放；
    /// 其余（任务栏重断言、最小化/独立最大化拉回）由 EnsureDockedState 处理。</summary>
    private void EnsureChildDocked(AttachSide side)
    {
        var child = ChildAt(side);
        if (child is null || !child.EnsureDockedState()) return;
        ReleaseHiddenSide(side);
    }

    /// <summary>子窗口自行隐藏（关闭/最小化到托盘类应用收到关闭后隐藏而非销毁）：解除吸附
    /// 外观并回吸附前矩形，保持隐藏——尊重应用意图，不把僵尸窗顶回屏幕（应用已认为自己
    /// 关闭，强拉回的窗不响应不重绘）。</summary>
    private void ReleaseHiddenSide(AttachSide side)
    {
        ChildAt(side)?.RestoreHidden();
        if (side == AttachSide.Left) _left = null; else _right = null;
        ShowNotice($"{(side == AttachSide.Left ? "左" : "右")}: 窗口已自行隐藏（可能已关闭到托盘），已自动释放");
        UpdateHostIcon();
    }

    private static string PaneTitle(IntPtr hwnd)
        => hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) ? "空" : Truncate(Native.GetTitle(hwnd), 40);

    private static string Truncate(string s, int max)
        => s.Length <= max ? s : s[..(max - 1)] + "…";
}
