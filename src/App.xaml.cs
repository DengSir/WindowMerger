using System.Globalization;
using System.Text.Json;
using System.Windows;

namespace WindowMerger;

/// <summary>启动参数（解析自命令行）：宿主模式目标、snap 接管直连句柄、实例隔离 profile、
/// 托盘/检测模式开关。</summary>
public sealed record StartupOptions
{
    public string? Left { get; set; }
    public string? Right { get; set; }
    public string? LeftExe { get; set; }
    public string? RightExe { get; set; }
    public long? LeftHwnd { get; set; }
    public long? RightHwnd { get; set; }
    public string? Profile { get; set; }
    public bool Tray { get; set; }
    public bool DetectSnap { get; set; }
    // snap 接管落位（两窗口可见边界并集，物理 px + 左右比例）：由 --left-hwnd/--right-hwnd 派生
    public ((double X, double Y, double W, double H) Rect, double Ratio)? Snap { get; set; }
}

public partial class App : Application
{
    /// <summary>
    /// 进程唯一身份（取自仓库属主，定死不再改——它会成为用户任务栏固定的身份，改名即分裂）。
    /// 本程序与生成的快捷方式都不写 System.AppUserModel.ID，AUMID 唯一来源就是这里，
    /// 快捷方式从此只按目标路径参与 pin/跳转列表，不再接管任务栏图标。
    /// </summary>
    private const string AppUserModelId = "DengSir.WindowMerger";

    private void OnStartup(object sender, StartupEventArgs e)
    {
        // 任何窗口创建之前（每进程仅一次；晚了或重复才失败，失败即编程错误，直接抛）
        int hr = Native.SetCurrentProcessExplicitAppUserModelID(AppUserModelId);
        if (hr != 0) throw new InvalidOperationException($"设置 AUMID 失败：0x{hr:X8}");

        var opts = ParseArgs(e.Args);
        if (opts.DetectSnap)
        {
            RunDetectSnap(); // 检测一次输出 JSON 即退出（测试/调试入口，与托盘共用检测代码）
            Shutdown();
            return;
        }
        if (opts.Tray)
        {
            // 托盘监听：无宿主窗口。ShutdownMode 必须显式——默认 OnLastWindowClose
            // 在零窗口下永不触发，应用会照常常驻；退出走 TrayController.Exit()
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            if (!new TrayController().Start()) Shutdown(); // 已有托盘实例 → 秒退
            return;
        }

        // 实例隔离：--profile 实例用独立 config，互不覆盖孤儿救援记录与几何
        ConfigStore.Configure(opts.Profile);
        var config = ConfigStore.Load();

        // snap 接管：直连句柄有效 → 宿主落位 = 并集矩形、比例 = 左窗宽占比（现场实测，
        // 不读 config 几何——那是常规实例的持久化值，接管几何由当前布局决定）
        if (opts.LeftHwnd is long lh && opts.RightHwnd is long rh
            && Native.IsWindow(new IntPtr(lh)) && Native.IsWindow(new IntPtr(rh)))
        {
            opts.Snap = SnapLayoutDetector.SnapRectFor(new IntPtr(lh), new IntPtr(rh));
        }
        // 接管实例不检查更新：多实例并发换装会互抢 .old，更新走用户手动启动的主实例
        if (opts.LeftHwnd is not null || opts.RightHwnd is not null) config.CheckUpdates = false;

        var host = new HostWindow(config, opts);
        MainWindow = host;
        host.Show();
    }

    /// <summary>--detect-snap：stdout 输出一行 JSON。reason 用 ASCII 报因码（CI cp1252
    /// 控制台安全），中文报因只进托盘 balloon（RunDetectSnap 不产 UI）。</summary>
    private static void RunDetectSnap()
    {
        try { Console.OutputEncoding = System.Text.Encoding.UTF8; } catch { /* 无控制台句柄时忽略 */ }
        var r = SnapLayoutDetector.DetectAndPick();
        object payload = r.Group is { } g
            ? new
            {
                ok = true,
                monitor = g.MonitorIndex,
                left = g.Windows[0].Hwnd.ToInt64(),
                right = g.Windows[1].Hwnd.ToInt64(),
                ratio = Math.Round(g.LeftFraction, 4),
            }
            : new { ok = false, reason = r.ReasonCode, detail = r.Reason };
        Console.WriteLine(JsonSerializer.Serialize(payload));
    }

    /// <summary>
    /// 命名参数 --left/-l、--right/-r、--left-exe、--right-exe（名字/PID/路径吸附，原语义不变）；
    /// --left-hwnd/--right-hwnd（snap 接管直连句柄，十进制或 0x 十六进制）；--profile（实例隔离）；
    /// --tray（托盘监听）、--detect-snap（检测一次输出退出）；其余位置参数按 [左] [右] 兜底。
    /// </summary>
    private static StartupOptions ParseArgs(string[] args)
    {
        var o = new StartupOptions();
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            if ((a is "--left" or "-l" or "/left" or "/l") && i + 1 < args.Length)
            {
                o.Left = args[++i];
            }
            else if ((a is "--right" or "-r" or "/right" or "/r") && i + 1 < args.Length)
            {
                o.Right = args[++i];
            }
            else if ((a is "--left-exe" or "/left-exe") && i + 1 < args.Length)
            {
                o.LeftExe = args[++i];
            }
            else if ((a is "--right-exe" or "/right-exe") && i + 1 < args.Length)
            {
                o.RightExe = args[++i];
            }
            else if ((a is "--left-hwnd" or "/left-hwnd") && i + 1 < args.Length)
            {
                o.LeftHwnd = ParseHwnd(args[++i]);
            }
            else if ((a is "--right-hwnd" or "/right-hwnd") && i + 1 < args.Length)
            {
                o.RightHwnd = ParseHwnd(args[++i]);
            }
            else if ((a is "--profile" or "/profile") && i + 1 < args.Length)
            {
                o.Profile = args[++i];
            }
            else if (a is "--tray" or "/tray")
            {
                o.Tray = true;
            }
            else if (a is "--detect-snap" or "/detect-snap")
            {
                o.DetectSnap = true;
            }
            else if (o.Left is null)
            {
                o.Left = a;
            }
            else if (o.Right is null)
            {
                o.Right = a;
            }
        }
        return o;
    }

    private static long? ParseHwnd(string raw)
    {
        raw = raw.Trim();
        if (raw.StartsWith("0x", StringComparison.OrdinalIgnoreCase))
        {
            return long.TryParse(raw[2..], NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var h) ? h : null;
        }
        return long.TryParse(raw, out var d) ? d : null;
    }
}
