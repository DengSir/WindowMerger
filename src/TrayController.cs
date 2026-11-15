using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Interop;
using Microsoft.Win32;
using WF = System.Windows.Forms;

namespace WindowMerger;

/// <summary>
/// 托盘控制器（tray 子命令 / 无参组合模式共用）：常驻、全局热键 Ctrl+Alt+M 捕捉"前台屏"的
/// snap 布局（检测在 SnapLayoutDetector），命中恰好 2 窗即 spawn 一个带 merge 子命令句柄
/// 参数的宿主实例接管。tray 子命令 = 零窗口纯托盘；组合模式（无参）= 托盘 + 默认宿主并存，
/// 宿主关窗后托盘继续常驻（首次关窗 balloon 提醒）。托盘菜单 = 设置枢纽：立即捕捉 / 打开
/// 主窗口 / 启动到托盘 / 开机自启（Run 表写无参命令，开机形态由「启动到托盘」勾选决定）/
/// 启动时检查更新 / 退出。设置开关经 App.Host 单一写者同步（宿主活着走宿主落盘，防整文件
/// 回写互相覆盖），宿主不在则直写默认 config.json。单实例（命名 mutex）；热键被占用时
/// 降级为菜单手动捕捉并 balloon 报因。
/// </summary>
internal sealed class TrayController
{
    private const int HotkeyId = 1;
    private const int WM_HOTKEY = 0x0312;
    private const int WsPopup = unchecked((int)0x80000000);
    private const int WsExToolwindow = 0x80;
    private static readonly IntPtr HwndMessage = new(-3); // message-only 父窗口：不进 z 序、不显示

    /// <summary>v1 固定 Ctrl+Alt+M（配置化留待有设置 UI 时再做）。</summary>
    public const uint HotkeyModifiers = Native.MOD_CONTROL | Native.MOD_ALT;
    public const uint HotkeyVirtualKey = 'M'; // VK_M 与 ASCII 同值

    public const string SingleInstanceMutexName = "Local\\WindowMerger.Tray.Instance";

    private const string RunKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string RunValueName = "WindowMerger";

    private Mutex? _singleInstance;
    private HwndSource? _messageWindow;
    private WF.NotifyIcon? _icon;
    private bool _residentHintShown; // 组合模式关窗常驻提醒只发一次
    private readonly Dictionary<int, Process> _captures = new(); // 显示器序号 → 已 spawn 的接管实例

    /// <summary>启动托盘。返回 false = 已有托盘实例在运行（调用方直接退出本进程）。</summary>
    public bool Start()
    {
        _singleInstance = new Mutex(true, SingleInstanceMutexName, out bool createdNew);
        if (!createdNew)
        {
            _singleInstance.Dispose();
            _singleInstance = null;
            return false;
        }

        // message-only 窗口承接 WM_HOTKEY
        var pars = new HwndSourceParameters("WindowMergerTray")
        {
            PositionX = 0,
            PositionY = 0,
            Width = 0,
            Height = 0,
            WindowStyle = WsPopup,
            ExtendedWindowStyle = WsExToolwindow,
            ParentWindow = HwndMessage,
        };
        _messageWindow = new HwndSource(pars);
        _messageWindow.AddHook(WndProc);

        _icon = new WF.NotifyIcon
        {
            Icon = LoadTrayIcon() ?? SystemIcons.Application,
            Text = "WindowMerger — Ctrl+Alt+M 捕捉 snap 布局",
            Visible = true,
        };
        _icon.ContextMenuStrip = BuildMenu();
        _icon.MouseDoubleClick += (_, _) => Capture();

        bool hotkeyOk = Native.RegisterHotKey(_messageWindow.Handle, HotkeyId, HotkeyModifiers, HotkeyVirtualKey);
        Balloon("WindowMerger 托盘已启动",
            hotkeyOk
                ? "按 Ctrl+Alt+M 捕捉当前 snap 布局（两个贴合排满屏幕的窗口）"
                : "热键注册失败（Ctrl+Alt+M 可能被其他程序占用），可右键托盘图标手动捕捉");

        return true;
    }

    /// <summary>检测 → spawn 接管实例；未命中按原因 balloon（检测细节见 SnapLayoutDetector）。</summary>
    private void Capture()
    {
        var result = SnapLayoutDetector.DetectAndPick();
        if (result.Group is not { } group)
        {
            Balloon("未捕捉 snap 布局", result.Reason);
            return;
        }

        // 同屏已有接管实例且还活着 → 不重复抓（两个实例抢同一批窗口会互相拆吸附态）
        if (_captures.TryGetValue(group.MonitorIndex, out var prev) && !prev.HasExited)
        {
            Balloon("未捕捉 snap 布局",
                $"屏 {group.MonitorIndex + 1} 已有接管实例（PID {prev.Id}）在运行，先关闭它再重捕");
            return;
        }

        string? exe = Environment.ProcessPath;
        if (string.IsNullOrEmpty(exe))
        {
            Balloon("未捕捉 snap 布局", "无法定位程序路径");
            return;
        }
        string args = $"merge --left-hwnd {group.Windows[0].Hwnd.ToInt64()} " +
                      $"--right-hwnd {group.Windows[1].Hwnd.ToInt64()} " +
                      $"--profile snap-{group.MonitorIndex}";
        try
        {
            var proc = Process.Start(new ProcessStartInfo(exe, args) { UseShellExecute = false })
                ?? throw new InvalidOperationException("Process.Start 返回 null");
            _captures[group.MonitorIndex] = proc;
            Balloon("已接管 snap 布局",
                $"屏 {group.MonitorIndex + 1}：2 个窗口已合并（关闭合并窗口即释放回原位）");
        }
        catch (Exception ex)
        {
            Balloon("接管失败", ex.Message);
        }
    }

    /// <summary>释放托盘全部资源（图标/热键/message 窗/单实例 mutex），不结束应用。
    /// Exit() = Teardown() + Application.Shutdown；换装重启前也用它先放掉 mutex
    /// （App.ShutdownTrayForRestart），新实例无参启动才能起组合模式托盘。</summary>
    public void Teardown()
    {
        if (_icon is not null)
        {
            _icon.Visible = false;
            _icon.Dispose();
            _icon = null;
        }
        if (_messageWindow is { } mw)
        {
            Native.UnregisterHotKey(mw.Handle, HotkeyId);
            mw.Dispose();
            _messageWindow = null;
        }
        _singleInstance?.ReleaseMutex();
        _singleInstance?.Dispose();
        _singleInstance = null;
    }

    public void Exit()
    {
        Teardown();
        System.Windows.Application.Current.Shutdown();
    }

    /// <summary>组合模式下宿主关窗后的一次性提醒（关窗常驻语义，merge 模式/测试屏蔽下
    /// 本进程无托盘，不进这里）。</summary>
    public void NotifyHostClosed()
    {
        if (_residentHintShown || _icon is null) return;
        _residentHintShown = true;
        Balloon("WindowMerger 仍在托盘运行",
            "窗口已关闭，热键 Ctrl+Alt+M 仍可用；右键托盘图标可重新打开窗口或退出");
    }

    // ---------- 托盘菜单 / 自启动 ----------

    private WF.ContextMenuStrip BuildMenu()
    {
        // 托盘从此读写默认 config.json（组合模式与 tray 子命令都不带 --profile，路径必然是
        // 默认值；Configure(null) 为 no-op，防御性调用保证顺序约定）
        ConfigStore.Configure(null);
        var config = ConfigStore.Load();
        var menu = new WF.ContextMenuStrip();

        var capture = new WF.ToolStripMenuItem("立即捕捉 snap 布局");
        capture.Click += (_, _) => Capture();
        menu.Items.Add(capture);

        var openHost = new WF.ToolStripMenuItem("打开主窗口");
        openHost.Click += (_, _) => (System.Windows.Application.Current as App)?.OpenDefaultHost();
        menu.Items.Add(openHost);

        menu.Items.Add(new WF.ToolStripSeparator());

        var startToTray = new WF.ToolStripMenuItem("启动到托盘")
        {
            CheckOnClick = true,
            Checked = config.StartToTray, // 勾选 = 下次无参启动不弹主窗，仅托盘常驻
        };
        startToTray.Click += (_, _) => ApplySetting(
            c => c.StartToTray = startToTray.Checked, h => h.SetStartToTray(startToTray.Checked));
        menu.Items.Add(startToTray);

        var autostart = new WF.ToolStripMenuItem("开机自启")
        {
            CheckOnClick = true,
            Checked = IsAutostartEnabled(),
        };
        autostart.Click += (_, _) => SetAutostart(autostart.Checked);
        menu.Items.Add(autostart);

        var checkUpdates = new WF.ToolStripMenuItem("启动时检查更新")
        {
            CheckOnClick = true,
            Checked = config.CheckUpdates, // 原主题菜单项迁移至此
        };
        checkUpdates.Click += (_, _) => ApplySetting(
            c => c.CheckUpdates = checkUpdates.Checked, h => h.SetCheckUpdates(checkUpdates.Checked));
        menu.Items.Add(checkUpdates);

        menu.Items.Add(new WF.ToolStripSeparator());
        var exit = new WF.ToolStripMenuItem("退出");
        exit.Click += (_, _) => Exit();
        menu.Items.Add(exit);
        return menu;
    }

    /// <summary>托盘菜单设置开关落盘：宿主活着时经宿主同步（单一写者——宿主 SaveConfig 整
    /// 文件回写会覆盖托盘直写的字段），否则直接 Load→改→Save 默认 config。</summary>
    private static void ApplySetting(Action<AppConfig> configSet, Action<HostWindow> hostSync)
    {
        ConfigStore.Configure(null);
        if (System.Windows.Application.Current is App { Host: { IsLoaded: true } host })
        {
            hostSync(host);
            return;
        }
        var cfg = ConfigStore.Load();
        configSet(cfg);
        ConfigStore.Save(cfg);
    }

    private static bool IsAutostartEnabled()
        => Registry.CurrentUser.OpenSubKey(RunKeyPath)?.GetValue(RunValueName) is not null;

    private static void SetAutostart(bool enable)
    {
        using var key = Registry.CurrentUser.CreateSubKey(RunKeyPath);
        if (enable)
        {
            string exe = Environment.ProcessPath ?? "";
            // 写无参命令 = 开机走组合模式：托盘常驻，是否弹主窗由「启动到托盘」勾选决定。
            // 旧条目（--tray 形式）继续可用（开机只托盘），用户重新勾选时自然升级
            key.SetValue(RunValueName, $"\"{exe}\"");
        }
        else
        {
            key.DeleteValue(RunValueName, false);
        }
    }

    // ---------- 基础设施 ----------

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WM_HOTKEY && wParam.ToInt32() == HotkeyId)
        {
            handled = true;
            Capture();
        }
        return IntPtr.Zero;
    }

    private void Balloon(string title, string text)
    {
        if (_icon is null) return;
        _icon.BalloonTipTitle = title;
        _icon.BalloonTipText = text;
        _icon.ShowBalloonTip(4000);
    }

    private static Icon? LoadTrayIcon()
    {
        try
        {
            var rs = System.Windows.Application.GetResourceStream(
                new Uri("pack://application:,,,/assets/WindowMerger.ico"));
            if (rs == null) return null;
            using var src = rs.Stream;
            using var ms = new MemoryStream(); // Icon(Stream) 要求可读且定位 0，资源流复制一份保险
            src.CopyTo(ms);
            ms.Position = 0;
            return new Icon(ms);
        }
        catch
        {
            return null; // 图标缺失只影响外观，按设计降级
        }
    }
}
