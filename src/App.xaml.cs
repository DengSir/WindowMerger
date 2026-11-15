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

    private TrayController? _tray; // 组合模式（无参启动）持有的托盘；merge/纯 tray/测试屏蔽下为 null
    private HostWindow? _host;     // 本进程默认宿主（组合模式关窗常驻 + 托盘「打开主窗口」用）

    /// <summary>组合模式的托盘（null = 本进程无托盘：merge 模式、纯 tray 模式或测试屏蔽）。</summary>
    internal TrayController? Tray => _tray;

    /// <summary>本进程默认宿主（null = 未开或已关窗；托盘菜单设置同步与「打开主窗口」用）。</summary>
    internal HostWindow? Host => _host;

    /// <summary>测试屏蔽：WM_NO_TRAY=1 时无参启动退回旧语义（仅主窗、关窗即退出），不起托盘
    /// 不占 mutex 不注册热键。复用 WM_UPDATE_OFF 的三层注入模式（wm.py 导入 / run_all / test.yml），
    /// 现存全部无参启动宿主的测试零改动；noargs_tray_test 自行剥掉该变量验证新语义。</summary>
    private static bool TraySuppressedForTests =>
        Environment.GetEnvironmentVariable("WM_NO_TRAY") == "1";

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
            Shutdown(); // 退出码保持 0
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

        // merge 显式吸附：窗口模式（OnMainWindowClose，关窗即退出——旧默认宿主语义）
        if (opts.Mode == LaunchMode.Merge)
        {
            ShowHost(new HostWindow(config, opts));
            return;
        }

        // 无参组合模式：托盘常驻（Ctrl+Alt+M 随时可用），按「启动到托盘」勾选决定是否弹主窗；
        // 关窗不退出（首次 balloon 提醒），托盘菜单「退出」才整进程结束
        if (!TraySuppressedForTests)
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _tray = new TrayController();
            if (!_tray.Start())
            {
                // 托盘 mutex 已被其他实例占用（双击 exe 再开一扇的兜底）：本实例退回纯窗口模式
                _tray = null;
                ShutdownMode = ShutdownMode.OnMainWindowClose;
            }
            else if (config.StartToTray)
            {
                return; // 勾选「启动到托盘」：零窗口，只有托盘常驻
            }
        }
        ShowHost(new HostWindow(config, opts));
    }

    private void ShowHost(HostWindow host)
    {
        MainWindow = host;
        _host = host;
        host.Show();
    }

    /// <summary>托盘「打开主窗口」：默认宿主还活着就激活，否则按默认 config 新建一扇
    /// （关窗常驻后重开 / 勾选「启动到托盘」后的唯一开窗途径之一）。同进程只保留一扇
    /// 默认宿主——两个实例/两扇窗会同写 config.json 互相覆盖。</summary>
    internal void OpenDefaultHost()
    {
        if (_host is { IsLoaded: true } alive)
        {
            if (alive.WindowState == WindowState.Minimized) alive.WindowState = WindowState.Normal;
            alive.Activate();
            return;
        }
        ConfigStore.Configure(null); // null = 默认 config.json（no-op 安全，防残留 profile 切换）
        ShowHost(new HostWindow(ConfigStore.Load(), new StartupOptions()));
    }

    /// <summary>换装重启前放掉托盘（图标/热键/message 窗/mutex 全量释放）：新实例无参启动
    /// 要起组合模式托盘，旧进程必须先释放 mutex，否则新实例误回退纯窗口模式丢托盘。</summary>
    internal void ShutdownTrayForRestart()
    {
        _tray?.Teardown();
        _tray = null;
    }

    /// <summary>换装失败回滚：重新拉起托盘（Teardown 已放掉全部资源，Start 全量重建；
    /// 热键被占等降级按 TrayController 既有路径 balloon 报因）。托盘回不来就退回
    /// 「关窗即退出」语义，不留无托盘的关窗常驻僵尸。WM_NO_TRAY=1（测试屏蔽）下不起
    /// 托盘、保持关窗即退出语义。</summary>
    internal void RestoreTrayForRetry()
    {
        if (_tray is not null) return;
        if (TraySuppressedForTests)
        {
            ShutdownMode = ShutdownMode.OnMainWindowClose;
            return;
        }
        var tray = new TrayController();
        if (tray.Start())
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _tray = tray;
        }
        else
        {
            ShutdownMode = ShutdownMode.OnMainWindowClose;
        }
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
