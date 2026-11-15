using System.Text.Json;
using System.Windows;

namespace WindowMerger;

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

        // 命令式 CLI（src/Cli.cs）：解析失败/请求用法都在开任何窗口前弹框收场——GUI 进程
        // 无控制台，lib 的报因与 help 输出不可见
        var parsed = Cli.Parse(e.Args);
        if (parsed.Help)
        {
            Cli.ShowUsage();
            Shutdown(); // ExitCode 保持 0
            return;
        }
        if (parsed.Errors.Length > 0)
        {
            Cli.ShowError(parsed.Errors);
            Shutdown(1); // 解析失败以非零退出码结束（WPF 无 Application.ExitCode，走 Shutdown(int)）
            return;
        }
        var opts = parsed.Options!;

        if (opts.Mode == LaunchMode.Detect)
        {
            RunDetectSnap(); // 检测一次输出 JSON 即退出（测试/调试入口，与托盘共用检测代码）
            Shutdown();
            return;
        }
        if (opts.Mode == LaunchMode.Tray)
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

        // merge 显式吸附与无参默认宿主当前同走窗口路径（无参组合模式在后续提交接入：
        // 托盘常驻 + 按「启动到托盘」勾选决定主窗）
        var host = new HostWindow(config, opts);
        MainWindow = host;
        host.Show();
    }

    /// <summary>detect 子命令：stdout 输出一行 JSON。reason 用 ASCII 报因码（CI cp1252
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
}
