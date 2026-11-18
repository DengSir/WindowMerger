using System.ComponentModel;
using System.IO;
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
    /// <summary>拖动钳制的每格最小宽度（DIP）：LCR 双比例下 0.2~0.8 区间允许中格缩到 4%，
    /// 联合钳制保证任何格子不低于此宽度。</summary>
    private const double MinPaneDip = 80;

    private const int WM_NCHITTEST = 0x0084;
    private const int WM_GETMINMAXINFO = 0x0024;
    private const int WM_SETTINGCHANGE = 0x001A;
    private const int HTCLIENT = 1;

    private double _ratio;
    private double _ratio2 = 0.5;   // 次比例（含义随布局：LCR 中格占比 / LTR·Quad 上下分界）
    private PaneLayoutDef _layout = PaneLayoutDef.LeftRight; // 当前布局（config Layout，非法回退 LR）

    private IntPtr _handle;
    private AttachedChild?[] _panes = Array.Empty<AttachedChild?>(); // 按布局格序持有的吸附态（null=空格）
    // 待落位的保存几何（物理像素）：hwnd 建好后 OnSourceInitialized 用 SetWindowPos 写入——
    // 不能在 hwnd 前设 DIP 属性（WPF 按初始主屏 DPI 解释，跨屏落位漂移）
    private (double X, double Y, double W, double H, bool Maximized)? _pendingPlacement;
    private DragAttach? _drag;
    private readonly DispatcherTimer _timer;
    private Point _lastOrigin;
    private int? _highlight;   // 当前拖放高亮的格子（null=无）
    private string? _notice;
    private DateTime _noticeUntil;

    // 窗格区动态元素（BuildPaneVisuals 按布局生成，SwitchLayout 重建）
    private Border[] _paneBorders = Array.Empty<Border>();
    private Border[] _paneHints = Array.Empty<Border>(); // 空格填充层（含提示文案 + 「选择窗口」按钮，可点击选窗）
    private Border[] _paneGlows = Array.Empty<Border>();
    private Border[] _dividers = Array.Empty<Border>();
    private readonly string? _windowAumid;      // 窗口级 AUMID（OnSourceInitialized 窗口可见前设置，
                                                // shell 按它分组任务栏按钮——多扇平级宿主各自独立按钮）

    // 自动更新（逻辑在 Updater.cs，这里只做状态机与 UI）
    private bool _checkUpdates;                 // 启动自动检查开关（构造时读 config.CheckUpdates；
                                                // 该字段归托盘所有、托盘菜单直写 config，宿主不再回写）
    private Updater.UpdateInfo? _update;        // 发现的可用更新（null=无）
    private string? _updateZip;                 // 已下载的更新包路径（null=未下载）
    private UpdatePhase _updatePhase = UpdatePhase.Idle;
    private bool _pendingInstall;               // 重启安装已确认：Closing 清理完成后换 exe

    /// <summary>当前生效的边框宽度：最大化时边框隐藏，格子铺满窗口。</summary>
    private double CurBorderW => WindowState == WindowState.Maximized ? 0 : _borderW;

    /// <summary>布局（当前布局的静态定义；字段别名，几何/命中/生成统一入口）。</summary>
    private PaneLayoutDef Layout => _layout;

    /// <summary>内容区尺寸（DIP，窗格可用 + 分隔条占地）：几何公式的基准，
    /// 从窗口 ActualWidth 直算——_content.ActualWidth 在布局回缩未完成时是旧值。</summary>
    private double ContentW => Math.Max(0, ActualWidth - 2 * CurBorderW);
    private double ContentH => Math.Max(0, ActualHeight - 2 * CurBorderW - TopInset);

    /// <summary>格 → 吸附态（null=空格）；越界安全（空数组/索引超限时返回 null）。</summary>
    private AttachedChild? ChildAt(int pane)
        => pane >= 0 && pane < _panes.Length ? _panes[pane] : null;

    private IntPtr HwndOf(int pane) => ChildAt(pane)?.Hwnd ?? IntPtr.Zero;

    /// <summary>格的中文名（状态栏/选择器/通知用）。</summary>
    private string PaneName(int pane)
        => pane >= 0 && pane < _layout.PaneNames.Length ? _layout.PaneNames[pane] : "?";

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

    /// <summary>新扇级联偏移：按落位屏 DPI 把 DIP 偏移换算成物理像素，位置平移后重新钳制
    /// 到该屏工作区（尺寸不变）。GetMonitorInfo 失败按原样返回（落位失败比偏移缺失更糟）。</summary>
    private static (double X, double Y, double W, double H, bool Maximized) CascadePlacement(
        (double X, double Y, double W, double H, bool Maximized) pl, double dip)
    {
        nint hMon = Native.MonitorFromPoint(
            new Native.POINT { X = (int)(pl.X + pl.W / 2), Y = (int)(pl.Y + pl.H / 2) },
            Native.MONITOR_DEFAULTTONEAREST);
        var mi = new Native.MONITORINFO { cbSize = Marshal.SizeOf<Native.MONITORINFO>() };
        if (!Native.GetMonitorInfo(hMon, ref mi)) return pl;
        double delta = dip * Native.MonitorDpiScale(hMon);
        var wa = mi.rcWork; // 物理 px
        double x = Math.Clamp(pl.X + delta, wa.Left, Math.Max(wa.Left, wa.Right - pl.W));
        double y = Math.Clamp(pl.Y + delta, wa.Top, Math.Max(wa.Top, wa.Bottom - pl.H));
        return (x, y, pl.W, pl.H, pl.Maximized);
    }

    public HostWindow(AppConfig config, StartupOptions? opts = null)
    {
        if (Enum.TryParse<AppThemeMode>(config.Theme, true, out var mode)) AppTheme.Mode = mode;
        // snap 接管计划优先：布局/双比例 = 检测形状匹配产物（接管 profile 持久化值只作回退）
        _layout = opts?.Snap?.Layout ?? PaneLayoutDef.FromConfig(config.Layout) ?? PaneLayoutDef.LeftRight;
        _ratio = Math.Clamp(config.Ratio, MinRatio, MaxRatio);
        _ratio2 = Math.Clamp(config.Ratio2, MinRatio, MaxRatio);
        _panes = new AttachedChild?[_layout.PaneCount];
        _checkUpdates = config.CheckUpdates;
        _windowAumid = (Application.Current as App)?.NextHostAumid();
        var orphanPids = config.AttachedPids;
        var orphanHwnds = config.AttachedHwnds;

        InitializeComponent();

        if (opts?.Snap is { } snap)
        {
            // snap 接管：宿主直接最大化（用户确认的最终行为），最大化矩形 = 布局所在屏
            // 工作区（各窗拼满工作区，接管必须罩住它们）。正常态几何**不取布局并集**——
            // 并集 ≈ 工作区会让"取消最大化"落回同样大的矩形（还原像没生效，用户实测
            // 质疑）；改取 profile 上次几何的宽高（还原后用户调过的大小），无/垃圾值
            // → 960×600 默认，居中于布局所在屏。布局与双比例 = 检测形状匹配产物
            // （legacy 双句柄路径布局恒 LR、ratio = 左窗宽占比），与宿主大小无关。
            nint hMon = Native.MonitorFromPoint(
                new Native.POINT { X = (int)(snap.Rect.X + snap.Rect.W / 2), Y = (int)(snap.Rect.Y + snap.Rect.H / 2) },
                Native.MONITOR_DEFAULTTONEAREST);
            var mi = new Native.MONITORINFO { cbSize = Marshal.SizeOf<Native.MONITORINFO>() };
            if (!Native.GetMonitorInfo(hMon, ref mi))
                throw new InvalidOperationException("snap 接管：布局所在屏工作区获取失败");
            var wa = mi.rcWork;
            double scale = Native.MonitorDpiScale(hMon);
            double maxW = Math.Max(MinWidth * scale, wa.Right - wa.Left);
            double maxH = Math.Max(MinHeight * scale, wa.Bottom - wa.Top);
            double w = 960 * scale, h = 600 * scale;
            if (config.WinLeft is double l && config.WinRight is double r
                && config.WinTop is double t && config.WinBottom is double b
                && r > l && b > t)
            {
                w = Math.Clamp(r - l, MinWidth * scale, maxW);
                h = Math.Clamp(b - t, MinHeight * scale, maxH);
            }
            int x = wa.Left + Math.Max(0, ((wa.Right - wa.Left) - (int)w) / 2);
            int y = wa.Top + Math.Max(0, ((wa.Bottom - wa.Top) - (int)h) / 2);
            _pendingPlacement = (x, y, w, h, true);
            _ratio = Math.Clamp(snap.Ratio, MinRatio, MaxRatio);
            _ratio2 = Math.Clamp(snap.Ratio2, MinRatio, MaxRatio);
        }
        else
        {
            // 几何恢复（Windows 原生惯例）：正常态矩形（物理像素）+ 是否最大化，校验钳制到
            // 可见显示器工作区后暂存，hwnd 建好后 OnSourceInitialized 落位——显示器断开/
            // 分辨率变化/配置损坏都不能产生屏外幽灵窗。无有效几何默认 960×600 主屏居中
            _pendingPlacement = ResolvePlacement(config);
            // 单实例唤起开新扇：多扇平级宿主恢复同一份保存几何会完全重叠，按 CascadeDip
            // 阶梯偏移让新扇可见（最大化态/无保存几何不偏移）
            if (_pendingPlacement is { } pl && !pl.Maximized && opts?.CascadeDip is double dip && dip > 0)
                _pendingPlacement = CascadePlacement(pl, dip);
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
        _revealTimer.Tick += (_, _) => { if (IsLoaded) PollTopBarReveal(); };

        LocationChanged += (_, _) => OnHostMoved();
        SizeChanged += (_, _) => { UpdatePaneVisuals(); ApplyLayout(); };
        StateChanged += (_, _) => OnStateChanged();
        Activated += (_, _) =>
        {
            EnsureAllChildrenDocked();
            RaiseChildrenBelow();
            // 宿主激活把宿主单独升到 z 序顶端，子窗口留在原地；低优先级再插回一次加固
            Dispatcher.BeginInvoke(RaiseChildrenBelow, DispatcherPriority.Background);
        };
        DpiChanged += (_, _) => ApplyLayout();
        Loaded += (_, _) => { UpdatePaneVisuals(); ApplyLayout(); CleanupOrphanedChildren(orphanPids, orphanHwnds); AttachStartupTargets(opts); };
        Closing += OnClosing;

        _timer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(250),
        };
        _timer.Tick += (_, _) => { if (IsLoaded) Maintain(); };

        // 关窗即停表：tick 排队期间宿主关闭 → 下一拍打在已断开的 Visual 上
        // （PointFromScreen 抛"未连接到 PresentationSource"→ 无全局处理器进程崩，
        // 2026-11-17/18 事件日志三次实锤；旧 merge 模式关窗即退出掩盖了它，
        // 组合模式关窗不退出 + 单进程多宿主频繁开关扇后暴露）。
        // IsLoaded tick 守卫是防排队竞态的第三层。
        Closed += (_, _) =>
        {
            _revealTimer.Stop();
            _timer.Stop();
        };

        // 上次更新的残留（.old/.update/临时 zip）：新实例启动即清；.old 可能仍被退出中的
        // 旧进程占用，删不掉定时重试自愈
        CleanupUpdateLeftoversWithRetry();

        // 启动自动检查更新：延迟 4 秒避开启动高峰，失败静默（离线/代理未就绪不打扰）。
        // 进程级一次性（App.TryBeginUpdateCheck 哨兵）：多宿主下只有第一扇发起检查——
        // 每扇都查会反复弹确认框；发现新版本经 App.BroadcastUpdate 同步其他扇顶条。
        // WM_UPDATE_OFF=1（wm.py 导入即注入 + run_all/CI）：测试宿主与真实 GitHub API
        // 彻底断网——发现新版本会自动弹模态确认框（抢焦点 + 禁用宿主 UI），测试环境
        // 必须不检查；update_e2e 剥掉本变量测真实流程，用 WM_UPDATE_API 指本地假服务
        if (Environment.GetEnvironmentVariable("WM_UPDATE_OFF") != "1"
            && (Application.Current as App)?.TryBeginUpdateCheck() != false)
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
        _dividerW = (double)FindResource("DividerW");

        // 窗格区按当前布局生成（窗格边框/提示/高亮/分隔条）
        BuildPaneVisuals();

        // 顶条左端应用图标
        _appIcon.Source = LoadAppIconFrame();

        // 顶条功能组：[更新组][布局×4][释放][主题] | [─][□][✕]
        // 静态字形直接写在 XAML；这里只挂接点击与动态字形（主题、最大化/还原）。
        // 选窗 = 点空格提示区（拖入或点击开选择器）；布局 = 四个直排按钮点按即切
        // （原下拉菜单退役，2026-11-16），重复点当前布局按钮 = SwitchLayout 早退无害
        _layoutLrButton.Click += (_, _) => SwitchLayout(PaneLayoutDef.LeftRight);
        _layoutLcrButton.Click += (_, _) => SwitchLayout(PaneLayoutDef.LeftCenterRight);
        _layoutLtrButton.Click += (_, _) => SwitchLayout(PaneLayoutDef.LeftTopRightBottom);
        _layoutQuadButton.Click += (_, _) => SwitchLayout(PaneLayoutDef.Quad);
        // 顶条「全部释放」：用户主动释放 → 全部子窗置顶回原位并激活最高序占用格的窗口
        // （两格布局即旧"右窗"语义）。前台只能转交一次（首次 SetForegroundWindow 已交出
        // 宿主的前台，第二次被前台锁拒绝），所以置顶走无激活 z 序、激活只做一次；
        // ReleaseAll 本体保持纯净——宿主关闭清理路径复用它，不拉前台
        _releaseButton.Click += (_, _) =>
        {
            var hwnds = _panes.Where(c => c is not null).Select(c => c!.Hwnd).ToList();
            ReleaseAll();
            foreach (var h in hwnds) RaiseReleasedWindow(h);
            if (hwnds.Count > 0) Native.SetForegroundWindow(hwnds[^1]);
        };
        SetThemeGlyph();
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

    /// <summary>主题按钮三态字形（Resources 集中定义的 IconThemeAuto/Dark/Light）：
    /// 按 AppTheme.Mode 换按钮 Content——同一 Grid 实例重复挂载幂等（单按钮独占引用）。</summary>
    private void SetThemeGlyph()
    {
        string key = AppTheme.Mode switch
        {
            AppThemeMode.Dark => "IconThemeDark",
            AppThemeMode.Light => "IconThemeLight",
            _ => "IconThemeAuto",
        };
        _themeButton.Content = Resources[key];
    }

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
        var menu = new ContextMenu
        {
            Template = MenuShellTemplate(), // 默认模板的白色圆角内边框不随主题，整体替换
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
        // 「启动时检查更新」已迁移至托盘菜单（托盘是常驻设置枢纽）
        menu.IsOpen = true;
    }

    private MenuItem ThemeMenuItem(string label, AppThemeMode mode, AppTheme.Palette p)
        => MenuItemWithCheck(label, AppTheme.Mode == mode, p, () =>
        {
            AppTheme.Mode = mode;
            ApplyTheme();
            // 模式是全局静态、刷色是每扇宿主自己的资源：多扇平级宿主要一改全改
            (Application.Current as App)?.BroadcastTheme(this);
            SaveConfig();
        });

    /// <summary>主题菜单通用项（主题三选）：极简模板 + 对勾列 + 悬停高亮。</summary>
    private MenuItem MenuItemWithCheck(string label, bool checkmark, AppTheme.Palette p, Action onClick)
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

        // 选中标志 = Fluent 对勾 E73E（固定宽度占位，未选中留空但保持文字对齐）；
        // FA 内嵌字体已整体退役，字形统一走 CaptionIcons（XAML 资源）
        var header = new StackPanel { Orientation = Orientation.Horizontal };
        header.Children.Add(new TextBlock
        {
            Text = checkmark ? "\uE73E" : "",
            FontFamily = (FontFamily)FindResource("CaptionIcons"),
            FontSize = 12,
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
        item.Click += (_, _) => onClick();
        return item;
    }

    /// <summary>按 AppTheme.Mode 重刷本窗主题资源（含主题按钮字形/tooltip）。多扇平级
    /// 宿主下由 App.BroadcastTheme 对其余扇广播调用，故为 internal。</summary>
    internal void ApplyTheme()
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
        SetThemeGlyph();
        _themeButton.ToolTip = ThemeTooltip();
    }

    private void SaveConfig()
    {
        // 多扇平级宿主共用默认 config：以磁盘为基底合并写，只覆盖本宿主自有字段——
        // 托盘自有字段（CheckUpdates/StartToTray，托盘菜单直写）与另一扇宿主刚写的内容
        // 原样保留，整文件回写互踩不再存在
        var cfg = ConfigStore.Load();
        cfg.Ratio = _ratio;
        cfg.Layout = _layout.ConfigName;
        cfg.Ratio2 = _ratio2;
        cfg.Theme = AppTheme.Mode.ToString();
        MergeOrphanRecords(cfg);
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

    /// <summary>孤儿救援记录合并（多扇平级宿主共用一份 config）：磁盘记录按条目过滤——
    /// 窗口存活 + 句柄未复用给其他进程 + corner 仍是吸附流程写入的直角化（DONOTROUND，
    /// 与 CleanupOrphanedChildren 同口径）——即"仍处吸附外观"的保留（可能是另一扇宿主
    /// 的子窗口）；已释放（corner 已还原 DEFAULT）与已死亡的条目剔除。再并上本宿主当前
    /// 子窗口记录（按 hwnd 去重）。</summary>
    private void MergeOrphanRecords(AppConfig cfg)
    {
        var pids = new List<long>();
        var hwnds = new List<long>();
        if (cfg.AttachedHwnds is { Count: > 0 } diskHwnds
            && cfg.AttachedPids is { Count: > 0 } diskPids
            && diskHwnds.Count == diskPids.Count)
        {
            for (int i = 0; i < diskHwnds.Count; i++)
            {
                if (!KeepOrphanRecord(new IntPtr(diskHwnds[i]), diskPids[i])) continue;
                pids.Add(diskPids[i]);
                hwnds.Add(diskHwnds[i]);
            }
        }
        foreach (var child in _panes)
        {
            if (child is null || hwnds.Contains(child.Hwnd.ToInt64())) continue;
            pids.Add((long)child.Pid);
            hwnds.Add(child.Hwnd.ToInt64());
        }
        cfg.AttachedPids = pids;
        cfg.AttachedHwnds = hwnds;
    }

    /// <summary>孤儿记录单条是否仍值得保留：窗口存活 + PID 匹配（防句柄复用）+ corner 仍是
    /// 吸附态直角化。读取失败按不保留处理（下次吸附会重新写入记录）。</summary>
    private static bool KeepOrphanRecord(IntPtr hwnd, long pid)
    {
        if (!Native.IsWindow(hwnd)) return false;
        Native.GetWindowThreadProcessId(hwnd, out uint actualPid);
        if (actualPid != (uint)pid) return false;
        return Native.DwmGetWindowAttribute(hwnd, Native.DWMWA_WINDOW_CORNER_PREFERENCE, out int pref, sizeof(int)) == 0
            && pref == Native.DWMWCP_DONOTROUND;
    }

    // （SetCheckUpdates/SetStartToTray 已随"单一写者"机制退役：SaveConfig 改合并写后，
    // 托盘菜单设置开关始终直写默认 config，宿主不再代写这两个托盘自有字段）

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
    /// Loaded → 吸附 → 拼图 的真实顺序用，模态 MessageBox 会泵 dispatcher 扭曲时序不能用。
    /// internal：DragAttach 的 WinEvent 时序也经此落盘。</summary>
    internal static void TracePoint(string msg)
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
        // 窗口级 AUMID 必须赶在窗口可见前设置（shell 首次编组任务栏按钮时读取）：
        // 多扇平级宿主各持唯一 AUMID → 任务栏各自独立按钮
        if (_windowAumid is not null)
            TracePoint($"SetWindowAumid hwnd={_handle.ToInt64():X} {Native.SetWindowAppUserModelId(_handle, _windowAumid)}");
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
        UpdateHostIcon("OnSourceInitialized"); // 初始即走统一图标管线（此刻 _panes 必空 → 内部落 SetFallbackIcon）
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

    /// <summary>关闭收尾 + 重启安装：先还原子窗口/落盘配置（孤儿记录随合并写按吸附外观
    /// 剔除本宿主条目）。非换装关闭：组合模式（托盘常驻）经托盘在最后一扇宿主关闭时发
    /// 一次性 balloon 提醒仍在运行；换装重启：先逐扇关闭其他宿主（各自还原子窗+落盘，
    /// 多扇平级宿主下不能留着它们与新实例并发收尾），再放掉托盘 mutex（新实例无参启动
    /// 要起组合模式托盘，mutex 被旧进程占着会走单实例唤起路径静默退场），换 exe 拉起
    /// 新实例后显式 Shutdown（组合模式 OnExplicitShutdown 下关窗不退出）。换装任何一步
    /// 失败都取消关闭（窗口留着）并报因，用户可重试或正常继续使用。</summary>
    private void OnClosing(object? sender, CancelEventArgs e)
    {
        OnClosingCleanup();
        var app = Application.Current as App;
        if (!_pendingInstall)
        {
            app?.NotifyHostClosed(this); // 多扇平级宿主：只有最后一扇真正关闭才触发托盘提醒（判断在 App）
            return;
        }
        try
        {
            app?.CloseOtherHosts(this);
            app?.ShutdownTrayForRestart();
            Updater.InstallAndRestart(_updateZip!);
            Application.Current.Shutdown();
        }
        catch (Exception ex)
        {
            e.Cancel = true;
            _pendingInstall = false;
            app?.RestoreTrayForRetry(); // teardown 已放掉 mutex/图标：取消关闭后必须重建托盘，否则关窗常驻变僵尸
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

        foreach (var child in _panes)
        {
            child?.MoveBy(dx, dy);
        }
    }

    private void ApplyLayout()
    {
        if (_handle == IntPtr.Zero || !IsLoaded) return;
        for (int i = 0; i < _panes.Length; i++)
        {
            ApplyLayoutTo(_panes[i], i);
        }
    }

    private bool ApplyLayoutTo(AttachedChild? child, int pane)
    {
        if (child is null || !child.CanPlace) return false;
        if (ActualWidth < 50 || ActualHeight < 50) return false;

        var (x, y, w, h) = PaneRectDevice(pane);

        // 外扩自身隐形边 + 插到宿主正下方，都在 child 内部完成
        return child.PlaceInPane(x, y, w, h);
    }

    /// <summary>格子的设备像素矩形：布局几何（内容区相对 DIP）经 PointToScreen 逐角转换。
    /// LR 布局公式与旧版逐值一致（净宽 = W-2bw-dv，左宽 = 净宽 × ratio）。</summary>
    private (int X, int Y, int W, int H) PaneRectDevice(int pane)
    {
        double bw = CurBorderW;
        var rects = Layout.PaneRects(ContentW, ContentH, _ratio, _ratio2, _dividerW);
        var r = rects[pane];
        var tl = PointToScreen(new Point(bw + r.X, bw + TopInset + r.Y));
        var br = PointToScreen(new Point(bw + r.X + r.Width, bw + TopInset + r.Y + r.Height));
        return ((int)Math.Round(tl.X), (int)Math.Round(tl.Y),
                (int)Math.Round(br.X - tl.X), (int)Math.Round(br.Y - tl.Y));
    }

    /// <summary>窗格视觉对账：按当前布局把窗格边框与分隔条摆到几何矩形上（Canvas 定位）。
    /// 用窗口 ActualWidth 直算（与 PaneRectDevice 同一公式），不能用 _content.ActualWidth——
    /// 最大化还原时 StateChanged 早于尺寸回缩完成，读到的旧值会把分隔条顶到错误位置。</summary>
    private void UpdatePaneVisuals()
    {
        if (_paneBorders.Length == 0) return;
        double cw = ContentW, ch = ContentH;
        var rects = Layout.PaneRects(cw, ch, _ratio, _ratio2, _dividerW);
        for (int i = 0; i < _paneBorders.Length; i++)
        {
            var r = rects[i];
            Canvas.SetLeft(_paneBorders[i], r.X);
            Canvas.SetTop(_paneBorders[i], r.Y);
            _paneBorders[i].Width = Math.Max(0, r.Width);
            _paneBorders[i].Height = Math.Max(0, r.Height);
        }
        var divs = Layout.DividerRects(cw, ch, _ratio, _ratio2, _dividerW);
        for (int i = 0; i < _dividers.Length; i++)
        {
            var (_, r) = divs[i];
            Canvas.SetLeft(_dividers[i], r.X);
            Canvas.SetTop(_dividers[i], r.Y);
            _dividers[i].Width = Math.Max(0, r.Width);
            _dividers[i].Height = Math.Max(0, r.Height);
        }
    }

    /// <summary>按当前布局生成窗格区元素（窗格边框 + 空格填充层/选择按钮 + 拖放高亮 + 分隔条），
    /// 旧元素整体丢弃重建。不碰 _panes（吸附态归属由构造/SwitchLayout 管理）。
    /// 主题刷色全部 SetResourceReference（DynamicResource 跟随 ApplyTheme）；
    /// 空格「选择窗口」按钮可点击 = 手动选窗入口（拖入吸附之外的第二条路，点选区域
    /// 2026-11-18 从整格收窄为按钮本体）。分隔条拖拽事件在此挂接
    /// （分隔条随布局增减，不能在 WireUi 一次性挂死）。</summary>
    private void BuildPaneVisuals()
    {
        _paneHost.Children.Clear();
        int n = _layout.PaneCount;
        _paneBorders = new Border[n];
        _paneHints = new Border[n];
        _paneGlows = new Border[n];

        for (int i = 0; i < n; i++)
        {
            // 空格占位 = 两层（2026-11-18 点选区域收窄）：填充层铺满整格（不透明 ThemeBar +
            // 提示文案，无点击处理器——误触不再弹模态选择器）+ 居中紧凑「选择窗口」按钮
            // （点选入口，尺寸 ≈78×31 DIP 兼容最小 80 DIP 格）。吸附后填充层隐藏恢复透明，
            // 子窗口要靠透明格子透出、点击穿透下去交互。按钮走 PaneHintStyle（XAML keyed
            // 样式）→ 有 AutomationPeer，UIA Invoke 可定位（选窗测试入口，与拖入吸附并行）
            var hintButton = new Button
            {
                Style = (Style)FindResource("PaneHintStyle"),
                Content = "选择窗口",
            };
            System.Windows.Automation.AutomationProperties.SetAutomationId(hintButton, $"_paneHint{i}");
            int pane = i; // for 循环变量跨迭代共享，闭包必须落局部副本（否则点击时 i==n 越界）
            hintButton.Click += (_, _) => Pick(pane);

            var hintText = new TextBlock
            {
                Text = "拖窗口到此处吸附",
                FontSize = 13,
                FontFamily = SystemFonts.MessageFontFamily,
                Margin = new Thickness(0, 0, 0, 12),
            };
            hintText.SetResourceReference(TextBlock.ForegroundProperty, "ThemeTextBrush");

            var hintStack = new StackPanel
            {
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
            };
            hintStack.Children.Add(hintText);
            hintStack.Children.Add(hintButton);

            var hintFill = new Border { Visibility = Visibility.Collapsed };
            hintFill.SetResourceReference(Border.BackgroundProperty, "ThemeBarBrush");
            hintFill.Child = hintStack;

            // 拖放目标高亮（拖动中亮起，盖在占位上）
            var glow = new Border
            {
                BorderBrush = new SolidColorBrush(Color.FromRgb(0x0A, 0x84, 0xFF)),
                BorderThickness = new Thickness(5),
                CornerRadius = new CornerRadius(4),
                Margin = new Thickness(1),
                IsHitTestVisible = false,
                Visibility = Visibility.Collapsed,
            };

            var inner = new Grid();
            inner.Children.Add(hintFill);
            inner.Children.Add(glow);

            var border = new Border
            {
                BorderThickness = new Thickness(1),
            };
            System.Windows.Automation.AutomationProperties.SetAutomationId(border, $"_paneBorder{i}");
            // 窗格包边 = ThemeBar 同色隐形 1px：盖住子窗自带透明边列（Electron 类 EFB 边列
            // 不渲染，ZCode 实测）与窗格矩形四缘——吸附区观感无边（用户定），画对比色会勾出格子框
            border.SetResourceReference(Border.BorderBrushProperty, "ThemeBarBrush");
            border.Child = inner;

            _paneHost.Children.Add(border);
            _paneBorders[i] = border;
            _paneHints[i] = hintFill;
            _paneGlows[i] = glow;
        }

        _dividers = new Border[_layout.DividerCount];
        var dividerStyle = (Style)FindResource("DividerStyle");
        for (int i = 0; i < _layout.DividerCount; i++)
        {
            var divider = new Border
            {
                Style = dividerStyle,
                Tag = i,
            };
            System.Windows.Automation.AutomationProperties.SetAutomationId(divider, $"_divider{i}");
            bool horizontal = Layout.DividerRects(1, 1, _ratio, _ratio2, _dividerW)[i].Axis == DividerAxis.Horizontal;
            divider.Cursor = horizontal ? Cursors.SizeNS : Cursors.SizeWE;
            // grip = Fluent More（横向三点）：点点**沿分隔条走向排列**（2026-11-16 用户确认，
            // 非"指示拖动方向"）——横条原样（…），竖条转 90° 成纵向三点（⋮）
            var grip = new TextBlock
            {
                Text = "\uE712",
                FontFamily = (FontFamily)FindResource("CaptionIcons"),
                FontSize = 10,
                Foreground = new SolidColorBrush(Color.FromArgb(0x70, 0xFF, 0xFF, 0xFF)),
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
                IsHitTestVisible = false,
            };
            if (!horizontal) grip.LayoutTransform = new RotateTransform(90); // 竖条 = 同字形转 90°
            divider.Child = grip;
            divider.MouseLeftButtonDown += DividerOnMouseDown;
            divider.MouseMove += DividerOnMouseMove;
            divider.MouseLeftButtonUp += DividerOnMouseUp;

            _paneHost.Children.Add(divider);
            _dividers[i] = divider;
        }
    }

    /// <summary>切换布局：子窗口按新旧格子矩形重叠面积迁移到最接近的新格（并列取低索引），
    /// 放不下（目标格已被占用）的释放回原位。随后重建窗格视觉、重摆、刷状态与图标并落盘。</summary>
    private void SwitchLayout(PaneLayoutDef next)
    {
        if (next == _layout) return;
        double cw = ContentW, ch = ContentH;
        var oldRects = _layout.PaneRects(cw, ch, _ratio, _ratio2, _dividerW);
        var newRects = next.PaneRects(cw, ch, _ratio, _ratio2, _dividerW);

        var newPanes = new AttachedChild?[next.PaneCount];
        for (int i = 0; i < _panes.Length; i++)
        {
            var child = _panes[i];
            if (child is null) continue;
            int best = -1;
            double bestArea = 0;
            for (int j = 0; j < newRects.Length; j++)
            {
                var o = Rect.Intersect(oldRects[i], newRects[j]);
                double area = o.IsEmpty ? 0 : o.Width * o.Height;
                if (area > bestArea)
                {
                    bestArea = area;
                    best = j;
                }
            }
            if (best >= 0 && newPanes[best] is null) newPanes[best] = child;
            else child.Restore(); // 多个子窗挤同一格：放不下的回原位
        }

        _layout = next;
        _panes = newPanes;
        _ratio = Math.Clamp(_ratio, MinRatio, MaxRatio);
        _ratio2 = Math.Clamp(_ratio2, MinRatio, MaxRatio);
        _highlight = null;
        BuildPaneVisuals();
        UpdatePaneVisuals();
        ApplyLayout();
        UpdateStatus();
        UpdateHostIcon("SwitchLayout");
        SaveConfig();
    }

    /// <summary>ContextMenu 极简外壳模板：默认模板有一层不随主题的白色圆角内边框，
    /// 整体替换为 Border+ItemsPresenter（主题菜单同款）。</summary>
    private static ControlTemplate MenuShellTemplate()
    {
        var menuTemplate = new ControlTemplate(typeof(ContextMenu));
        var menuBorder = new FrameworkElementFactory(typeof(Border));
        menuBorder.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(ContextMenu.BackgroundProperty));
        menuBorder.SetValue(Border.BorderBrushProperty, new TemplateBindingExtension(ContextMenu.BorderBrushProperty));
        menuBorder.SetValue(Border.BorderThicknessProperty, new TemplateBindingExtension(ContextMenu.BorderThicknessProperty));
        menuBorder.SetValue(Border.PaddingProperty, new TemplateBindingExtension(ContextMenu.PaddingProperty));
        menuBorder.AppendChild(new FrameworkElementFactory(typeof(ItemsPresenter)));
        menuTemplate.VisualTree = menuBorder;
        return menuTemplate;
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
        // 插到宿主正下方（从最高格序往回插，最终顺序上→下：宿主、格 0、格 1…）。
        // 不用 HWND_TOP：实测 Alt+Tab 切回宿主后它是静默无效调用（返回 true 但 z 序不变）
        for (int i = _panes.Length - 1; i >= 0; i--)
        {
            _panes[i]?.PlaceBelowHost();
        }
    }

    private void FixZOrder()
    {
        // 宿主正下方必须是连续的"可见子窗口块"（次序不限）：Alt+Tab 切回时宿主单独升顶，
        // 子窗口留在原地会被切走前的前台窗口压住（宿主内 HWND_TOP 拉起实测无效），不满足
        // 就整体插回宿主正下方。最小化（移出屏幕外但非 iconic）的子窗口豁免。
        // 跳过隐藏/cloaked 窗口：它们不渲染、不参与命中，为它们翻转子窗口 z 纯属浪费，
        // 且每次写入都是一次 DWM 重合成（闪烁）——与 IsCoveredAtCursor 同一判定标准。
        var children = _panes.Where(c => c is not null).ToArray();
        if (children.Length == 0) return;
        var matched = new bool[children.Length];
        IntPtr below = _handle == IntPtr.Zero ? IntPtr.Zero : Native.GetWindow(_handle, Native.GW_HWNDNEXT);
        for (int seen = 0, hops = 0; seen < children.Length && below != IntPtr.Zero && hops < 32; hops++)
        {
            if (!Native.IsWindowVisible(below) || Native.IsCloaked(below))
            {
                below = Native.GetWindow(below, Native.GW_HWNDNEXT);
                continue;
            }
            for (int i = 0; i < children.Length; i++)
            {
                if (below == children[i]!.Hwnd) matched[i] = true;
            }
            seen++;
            below = Native.GetWindow(below, Native.GW_HWNDNEXT);
        }
        bool needRaise = false;
        for (int i = 0; i < children.Length; i++)
        {
            var c = children[i]!;
            if (c.IsAlive && !Native.IsIconic(c.Hwnd) && !matched[i])
            {
                needRaise = true;
                break;
            }
        }
        if (needRaise) RaiseChildrenBelow();
    }

    private void Maintain()
    {
        bool childLost = false;
        for (int i = 0; i < _panes.Length; i++)
        {
            if (_panes[i] is { } child && !child.IsAlive)
            {
                TracePoint($"Maintain childLost pane={i} hwnd={child.Hwnd}");
                _panes[i] = null;
                childLost = true;
            }
        }
        UpdateStatus();
        if (childLost) { UpdateHostIcon("childLost"); }

        if (WindowState == WindowState.Minimized) return; // 最小化时不布局；最大化也要自愈
        bool dragging = _drag is { IsBusy: true };
        if (!dragging && _highlight is not null) SetDragHighlight(null); // 拖动事件丢失时兜底熄灭高亮
        if (dragging) return; // 有窗口正在被拖动，不对抗

        // 吸附态外观自愈：任务栏隐藏标记可能被 shell 侧重新收录（无查询接口，见
        // EnsureDockedState 的低频重断言）；吸附子窗口没有任务栏按钮，最小化后无从手动
        // 还原；独立最大化则摧毁合并布局——宿主可见期间一律拉回格子自愈（子窗口自身
        // 没有"最大化"概念）。例外：应用自行隐藏（关闭/最小化到托盘类）→ 上报后走
        // 释放还原，不拉回（见 ReleaseHiddenSide）
        EnsureAllChildrenDocked();

        UpdatePaneVisuals(); // 分隔条视觉位置与比例的持续对账（自愈任何布局漂移）
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
                foreach (var child in _panes)
                {
                    child?.MoveOffscreen();
                }
                break;

            case WindowState.Maximized:
            case WindowState.Normal:
                // 最大化只改布局：吸附窗口随格子放大，不触发系统最大化；边框同步隐藏/恢复。
                // 立即按当前窗口宽校一次；WPF 尺寸回缩/边框变化完成后再校一次（Loaded 优先级），
                // 消除事件时序导致的分隔条位置漂移
                EnsureAllChildrenDocked();
                if (_outer is not null) _outer.BorderThickness = new Thickness(CurBorderW);
                UpdatePaneVisuals();
                ApplyLayout();
                Dispatcher.BeginInvoke(() => { UpdatePaneVisuals(); ApplyLayout(); }, DispatcherPriority.Loaded);
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
        // 浮层态画上/左/右 1 DIP 框（底边由 _topBar 自带底线提供，常驻；正常态无框——顶条
        // 底边线即标题栏底边）。框画在 _topBarFrame（_topBar 外面），_topBar.Height 恒 29
        // 不动：底色带视觉高度与正常态一致，边框不侵占顶条本体
        const double barFrame = 1;
        _topBarFrame.BorderThickness = overlay ? new Thickness(barFrame, barFrame, barFrame, 0) : default;
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

    /// <summary>宿主图标 = 子窗口图标按布局象限槽位合成（caller 供 trace 定位调用方）。</summary>
    private void UpdateHostIcon(string caller = "?")
    {
        // 各格图标素材（取不到的格用应用图标占位——一眼能看出哪格空着）
        var sources = new BitmapSource?[_panes.Length];
        for (int i = 0; i < _panes.Length; i++)
        {
            sources[i] = TryGetIconSource(_panes[i]?.Hwnd ?? IntPtr.Zero);
        }
        TracePoint($"UpdateHostIcon[{caller}]: panes={_panes.Length} 素材={sources.Count(s => s != null)} " +
                   $"hwnds={string.Join("/", _panes.Select(c => c?.Hwnd.ToInt64() ?? 0))}");
        if (sources.All(s => s == null))
        {
            SetFallbackIcon(); // 无吸附窗口时回到应用图标（而非默认 WPF 图标）
            return;
        }

        BitmapSource? app = LoadAppIconFrame();
        if (app is null)
        {
            Icon = OnTaskbarCanvas(sources.First(s => s != null)!); // 应用图标资源损坏时退化到现有源
            return;
        }

        // 象限合成：按布局 IconSlots 把各格图标画进 2×2 象限（各自锚定象限外角），
        // 按槽位序绘制——两格布局与旧版双子对角合成逐像素一致（右上先画在下、左下后画盖顶）。
        // 画布随任务栏 DPI（子图标：≤2 格 3/4、3/4 格 1/2）
        var (w, h) = TaskbarIconSize();
        double cell = Math.Min(w, h);
        double iconSize = sources.Length <= 2 ? cell * 3 / 4 : cell / 2;
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            for (int slot = 0; slot < 4; slot++)
            {
                int pane = Array.IndexOf(_layout.IconSlots, slot);
                if (pane < 0) continue;
                var src = sources[pane] ?? app;
                double x = slot % 2 == 0 ? 0 : cell - iconSize; // 左列贴左、右列贴右
                double y = slot < 2 ? 0 : cell - iconSize;      // 上行贴顶、下行贴底
                dc.DrawImage(src, new Rect(x, y, iconSize, iconSize));
            }
        }
        var rtb = new RenderTargetBitmap(w, h, 96, 96, PixelFormats.Pbgra32);
        rtb.Render(visual);
        rtb.Freeze();
        Icon = rtb;
    }

    // 吸附编排（TryAttach/Release*/Pick 及 CLI 匹配）见 HostWindow.Attach.cs
    // 拖拽交互（顶条拖动/最大化拖动还原/分隔条拖动）见 HostWindow.Drag.cs

    // ---------- 自动更新（网络/换装逻辑在 Updater.cs） ----------

    private enum UpdatePhase { Idle, Checking, Available, Downloading }

    /// <summary>更新组状态：无更新/检查失败（Idle/Checking）时按钮+文案+左分隔线整体隐藏不占顶条，
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
                // Checking/Idle 恒隐藏，字形不显示——仍换 Fluent Sync（按钮字体是 CaptionIcons，
                // 留 FA 码点会在万一现身时渲染成豆腐块）
                enabled = false; visible = false; glyph = "\uE72C"; label = "正在检查更新…";
                break;
            case UpdatePhase.Available:
                enabled = true; visible = true; glyph = "\uE896"; // Fluent Download
                label = _updateZip is not null
                    ? $"已下载 {version}，点击安装"
                    : $"发现新版本 {version}，点击下载安装";
                break;
            case UpdatePhase.Downloading:
                enabled = false; visible = true; glyph = "\uE896"; label = "下载更新中…";
                break;
            default: // Idle：无更新不显示图标
                enabled = true; visible = false; glyph = "\uE72C";
                label = $"检查更新（当前 {Updater.CurrentDisplayVersion()}）";
                break;
        }
        _updateButton.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
        _updateLabel.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
        _updateSeparator.Visibility = visible ? Visibility.Visible : Visibility.Collapsed; // 左分隔线与组一体显隐
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

    /// <summary>接收进程内首扇广播的可用更新（多宿主：自动检查只由第一扇发起，其他扇经此
    /// 同步顶条 ⬇；不弹确认框——点 ⬇ 直接下载，与"取消后随时可点"同语义）。仅 Idle 态
    /// 接收：广播总发生在其他扇 Idle 时，防御性守卫防未来时序变化下覆盖进行中的状态。</summary>
    internal void AdoptUpdate(Updater.UpdateInfo info)
    {
        if (_updatePhase != UpdatePhase.Idle) return;
        _update = info;
        SetUpdatePhase(UpdatePhase.Available);
    }

    /// <summary>启动唯一一次检查 GitHub 最新 Release：发现新版本 → Available（顶条现身
    /// 「发现新版本 ⬇」）并直接弹确认框——一次性宣告，确认或点 ⬇ 都直接下载安装，
    /// 取消后顶条按钮随时可再点。无更新/失败静默——更新组保持隐藏（离线、代理未就绪
    /// 不打扰）。检查异常由 AutoCheckUpdate 吞掉。发现新版本经 App.BroadcastUpdate
    /// 同步进程内其他存活宿主顶条（它们不检查、也不弹框）。</summary>
    private async Task CheckUpdateAsync()
    {
        SetUpdatePhase(UpdatePhase.Checking);
        var check = await Updater.CheckLatestAsync();
        if (check.Update is { } info)
        {
            _update = info;
            SetUpdatePhase(UpdatePhase.Available);
            (Application.Current as App)?.BroadcastUpdate(this, info);
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
            if (_panes.All(c => c is null))
            {
                _status.Text = "把任意窗口拖进来吸附，或点击「选择窗口」按钮";
            }
            else
            {
                _status.Text = string.Join("    ", Enumerable.Range(0, _panes.Length)
                    .Select(i => $"{PaneName(i)}: {PaneTitle(_panes[i]?.Hwnd ?? IntPtr.Zero)}"));
            }
        }
        UpdatePaneHints();
    }

    /// <summary>空格显示填充与提示文案（不再透明穿透）；该格吸附后隐藏占位恢复透明——
    /// 子窗口要靠透明格子透出、点击穿透下去交互，吸附格必须回到透明。</summary>
    private void UpdatePaneHints()
    {
        for (int i = 0; i < _paneHints.Length; i++)
        {
            _paneHints[i].Visibility = _panes[i] is null ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    private void ShowNotice(string text)
    {
        _notice = text;
        _noticeUntil = DateTime.UtcNow + TimeSpan.FromSeconds(3);
        UpdateStatus();
    }

    private static bool IsCtrlHeld()
        => Keyboard.IsKeyDown(Key.LeftCtrl) || Keyboard.IsKeyDown(Key.RightCtrl);

    /// <summary>释放后把窗口置顶（无激活）：Restore 把窗口放回普通层且不带 z 序写入，
    /// 窗口常埋在其他窗口后面，先保证可见。z 序重排不受前台锁限制（受限的是激活）。</summary>
    private static void RaiseReleasedWindow(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || !Native.IsWindow(hwnd)) return;
        Native.SetWindowPos(hwnd, Native.HwndTop, 0, 0, 0, 0,
            Native.SWP_NOMOVE | Native.SWP_NOSIZE | Native.SWP_NOACTIVATE
            | Native.SWP_NOOWNERZORDER);
    }

    /// <summary>全部占用格的吸附态自愈入口：应用自行隐藏（连续两个维护周期不可见）→ 走释放；
    /// 其余（任务栏重断言、最小化/独立最大化拉回）由 EnsureDockedState 处理。</summary>
    private void EnsureAllChildrenDocked()
    {
        for (int i = 0; i < _panes.Length; i++)
        {
            var child = _panes[i];
            if (child is null || !child.EnsureDockedState()) continue;
            ReleaseHiddenSide(i);
        }
    }

    /// <summary>子窗口自行隐藏（关闭/最小化到托盘类应用收到关闭后隐藏而非销毁）：解除吸附
    /// 外观并回吸附前矩形，保持隐藏——尊重应用意图，不把僵尸窗顶回屏幕（应用已认为自己
    /// 关闭，强拉回的窗不响应不重绘）。</summary>
    private void ReleaseHiddenSide(int pane)
    {
        TracePoint($"ReleaseHiddenSide pane={pane}");
        ChildAt(pane)?.RestoreHidden();
        if (pane >= 0 && pane < _panes.Length) _panes[pane] = null;
        ShowNotice($"{PaneName(pane)}: 窗口已自行隐藏（可能已关闭到托盘），已自动释放");
        UpdateHostIcon("ReleaseHiddenSide");
    }

    private static string PaneTitle(IntPtr hwnd)
        => hwnd == IntPtr.Zero || !Native.IsWindow(hwnd) ? "空" : Truncate(Native.GetTitle(hwnd), 40);

    private static string Truncate(string s, int max)
        => s.Length <= max ? s : s[..(max - 1)] + "…";
}
