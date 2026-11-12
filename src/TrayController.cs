using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Interop;
using Microsoft.Win32;
using WF = System.Windows.Forms;

namespace WindowMerger;

/// <summary>
/// 托盘监听模式（--tray）：常驻、无宿主窗口，全局热键 Ctrl+Alt+M 捕捉"前台屏"的 snap 布局
/// （检测在 SnapLayoutDetector），命中恰好 2 窗即 spawn 一个带 --left-hwnd/--right-hwnd/
/// --profile 的宿主实例接管。主程序关闭语义不变（关宿主 = 释放子窗口并退出），热键监听
/// 独立常驻；托盘自身退出在右键菜单。单实例（命名 mutex）；热键被占用时降级为菜单手动
/// 捕捉并 balloon 报因。托盘只读默认 config，不写（不产生孤儿记录/几何干扰）。
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
        string args = $"--left-hwnd {group.Windows[0].Hwnd.ToInt64()} " +
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

    public void Exit()
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
        System.Windows.Application.Current.Shutdown();
    }

    // ---------- 托盘菜单 / 自启动 ----------

    private WF.ContextMenuStrip BuildMenu()
    {
        var menu = new WF.ContextMenuStrip();
        var capture = new WF.ToolStripMenuItem("立即捕捉 snap 布局");
        capture.Click += (_, _) => Capture();
        var autostart = new WF.ToolStripMenuItem("开机自启（托盘）")
        {
            CheckOnClick = true,
            Checked = IsAutostartEnabled(),
        };
        autostart.Click += (_, _) => SetAutostart(autostart.Checked);
        var exit = new WF.ToolStripMenuItem("退出");
        exit.Click += (_, _) => Exit();
        menu.Items.Add(capture);
        menu.Items.Add(autostart);
        menu.Items.Add(new WF.ToolStripSeparator());
        menu.Items.Add(exit);
        return menu;
    }

    private static bool IsAutostartEnabled()
        => Registry.CurrentUser.OpenSubKey(RunKeyPath)?.GetValue(RunValueName) is not null;

    private static void SetAutostart(bool enable)
    {
        using var key = Registry.CurrentUser.CreateSubKey(RunKeyPath);
        if (enable)
        {
            string exe = Environment.ProcessPath ?? "";
            key.SetValue(RunValueName, $"\"{exe}\" --tray");
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
