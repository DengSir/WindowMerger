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
    internal const string AppUserModelId = "DengSir.WindowMerger";

    private TrayController? _tray;                  // 组合模式（无参启动）持有的托盘；merge/纯 tray/测试屏蔽下为 null
    private readonly List<HostWindow> _hosts = new(); // 本进程全部存活宿主（平级无主次；关窗常驻/唤起开新扇/换装清理用）
    private bool _updateCheckStarted;               // 进程级一次性哨兵：更新检查只由第一扇宿主发起
    private int _hostAumidSeq;                      // 进程内宿主窗口级 AUMID 序号（多扇独立任务栏按钮）

    /// <summary>新宿主的窗口级 AUMID：pid + 进程内序号保全系统唯一——shell 任务栏按钮按
    /// AUMID 分组，多扇平级宿主（含跨进程的 snap 接管实例）各得独立按钮，不受用户任务栏
    /// "合并按钮"设置影响。</summary>
    internal string NextHostAumid() => $"{AppUserModelId}.host-{Environment.ProcessId}-{++_hostAumidSeq}";

    /// <summary>组合模式的托盘（null = 本进程无托盘：merge 模式、纯 tray 模式或测试屏蔽）。</summary>
    internal TrayController? Tray => _tray;

    /// <summary>本进程存活宿主快照（多扇平级；换装清理用）。</summary>
    internal IReadOnlyList<HostWindow> Hosts => _hosts;

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

        var config = ConfigStore.Load();

        // 无参组合模式：托盘常驻（Ctrl+Alt+M 随时可用；snap 捕捉进程内直开接管宿主），
        // 按「启动到托盘」勾选决定是否弹主窗；关窗不退出（最后一扇宿主关闭时 balloon
        // 提醒），托盘菜单「退出」才整进程结束
        if (!TraySuppressedForTests)
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _tray = new TrayController();
            if (!_tray.Start())
            {
                // 单实例：主实例在运行（mutex 被占）→ 唤起它开一扇新的平级宿主，本进程退出。
                // 绝不回退纯窗口模式开第二进程（旧"双击 exe 再开一扇"语义已退役）
                TrayController.SignalOpenHost();
                Shutdown(); // rc 0，与 tray 子命令第二实例秒退一致
                return;
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
        _hosts.Add(host);
        host.Closed += (_, _) => _hosts.Remove(host);
        host.Show();
    }

    /// <summary>托盘「打开新窗口」/ 单实例唤起入口：每次开一扇**新的平级宿主**（无宿主时即
    /// 常规开窗；多扇宿主恢复同一份保存几何会完全重叠，按存活扇数级联偏移让新扇可见）。</summary>
    internal void OpenNewHost()
    {
        var alive = _hosts.Count(h => h.IsLoaded);
        ShowHost(new HostWindow(ConfigStore.Load(), new StartupOptions
        {
            CascadeDip = Math.Min(alive, 8) * 24,
        }));
    }

    /// <summary>托盘捕捉 snap 布局：进程内直开一扇接管宿主（单进程多宿主，与普通新扇平级；
    /// 旧"spawn merge 子进程 + profile 配置隔离"已退役——接管宿主共用默认 config，
    /// 孤儿救援记录也进默认表，救援口径更全）。宿主 ctor 按种子跳过 config 几何恢复、
    /// 布局/双比例覆盖、直接最大化在布局所在屏。返回 null = 宿主构造失败（屏信息获取失败）。</summary>
    internal HostWindow? OpenSnapHost(SnapLayoutDetector.SnapGroup group)
    {
        var seed = new StartupOptions
        {
            Snap = SnapLayoutDetector.PlanFromGroup(group),
            PaneHwnds = group.Windows.Select(w => w.Hwnd.ToInt64()).ToList(),
        };
        try
        {
            var host = new HostWindow(ConfigStore.Load(), seed);
            ShowHost(host);
            return host;
        }
        catch (InvalidOperationException)
        {
            return null; // 布局所在屏工作区获取失败（ctor 明确抛出）
        }
    }

    /// <summary>宿主关闭通知转发：多扇平级宿主下单关一扇不提醒，只有最后一扇真正关闭才
    /// 触发托盘的关窗常驻一次性 balloon。</summary>
    internal void NotifyHostClosed(HostWindow closing)
    {
        if (_hosts.Any(h => h != closing && h.IsLoaded)) return;
        Tray?.NotifyHostClosed();
    }

    /// <summary>主题切换广播：模式是全局静态、刷色是每扇宿主自己的资源——多扇平级宿主
    /// 一改全改（ApplyTheme 含字形/tooltip 同步）。</summary>
    internal void BroadcastTheme(HostWindow source)
    {
        foreach (var h in _hosts.Where(h => h != source && h.IsLoaded))
        {
            h.ApplyTheme();
        }
    }

    /// <summary>换装重启前关闭其他存活宿主：逐扇 Close()（各自 OnClosing 还原子窗+落盘）。
    /// 多扇平级宿主下不能留着它们与换装后的新实例并发收尾。</summary>
    internal void CloseOtherHosts(HostWindow except)
    {
        foreach (var h in _hosts.Where(h => h != except && h.IsLoaded).ToList())
        {
            h.Close();
        }
    }

    /// <summary>进程级更新检查哨兵：返回 true = 本扇获得检查权（进程内第一扇构造的宿主）。
    /// 多宿主下每次开新扇都检查会反复弹确认框打扰（检查权收归进程一次）。</summary>
    internal bool TryBeginUpdateCheck()
    {
        if (_updateCheckStarted) return false;
        _updateCheckStarted = true;
        return true;
    }

    /// <summary>首扇自动检查发现新版本后同步到其他存活宿主顶条：只同步 Available 态与
    /// UpdateInfo——其他扇不重复弹确认框（一次性宣告只属于发起扇），点 ⬇ 直接下载与
    /// "取消后随时可点"同语义；下载/安装状态由发起扇独自推进，换装前 CloseOtherHosts 收尾。</summary>
    internal void BroadcastUpdate(HostWindow source, Updater.UpdateInfo info)
    {
        foreach (var h in _hosts.Where(h => h != source && h.IsLoaded))
        {
            h.AdoptUpdate(info);
        }
    }

    /// <summary>换装重启前放掉托盘（图标/热键/message 窗/mutex 全量释放）：新实例无参启动
    /// 要起组合模式托盘，旧进程必须先释放 mutex——否则新实例会走单实例唤起路径静默退场，
    /// 托盘就丢了。</summary>
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
                layout = g.Layout.ConfigName,
                left = g.Windows[0].Hwnd.ToInt64(),
                right = g.Windows[1].Hwnd.ToInt64(),
                panes = g.Windows.Select(w => w.Hwnd.ToInt64()).ToArray(),
                ratio = Math.Round(g.Ratio, 4),
                ratio2 = Math.Round(g.Ratio2, 4),
            }
            : new { ok = false, reason = r.ReasonCode, detail = r.Reason };
        Console.WriteLine(JsonSerializer.Serialize(payload));
    }
}
