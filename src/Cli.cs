using System.CommandLine;
using System.Windows;

namespace WindowMerger;

/// <summary>启动模式（命令式子命令）：Cli.Parse 时由命中的子命令动作填写。None = 无命令
/// 动作命中（lib 已按内建 help 处理，GUI 下由 ShowUsage 弹框收场）。merge/tray 子命令已随
/// "单进程多宿主 + 进程内 snap 接管"重构退役（2026-11-18）：吸附全走 UI（拖入/空格提示/
/// 托盘捕捉），纯托盘常驻 = 无参 + 「启动到托盘」勾选。</summary>
public enum LaunchMode
{
    None,
    /// <summary>无参启动：托盘常驻 + 按「启动到托盘」勾选决定是否弹默认宿主；关窗不退出。</summary>
    Combined,
    /// <summary>检测一次 snap 布局，stdout 输出一行 JSON 后退出（CI/调试入口）。</summary>
    Detect,
}

/// <summary>启动参数：CLI 解析只产生模式。Snap/PaneHwnds = snap 接管种子，由托盘进程内
/// 直开接管宿主时经 App.OpenSnapHost 填写（CLI 不再产生——旧 merge 句柄参数已退役）。</summary>
public sealed record StartupOptions
{
    public LaunchMode Mode { get; set; } = LaunchMode.None;
    // 单实例唤起开新扇的级联偏移（DIP，按存活宿主扇数阶梯）：仅无参唤起路径由 App 填写，
    // CLI 解析不产生该值——多扇平级宿主同几何会完全重叠，偏移让新扇可见
    public double CascadeDip { get; set; }
    // snap 接管落位计划（并集矩形物理 px + 布局 + 双比例）与 pane 序句柄：进程内直开宿主时填写
    public SnapPlan? Snap { get; set; }
    public IReadOnlyList<long>? PaneHwnds { get; set; }
}

/// <summary>Cli.Parse 结果：Help = 请求了用法（--help，动作未执行）；Errors 非空 = 解析
/// 失败；两者皆空时 Options 必非 null（Mode 已由命中的子命令动作填写）。</summary>
public sealed record CliParseResult(StartupOptions? Options, string[] Errors, bool Help);

/// <summary>命令式 CLI（System.CommandLine）：根命令无参 = 组合模式，子命令 detect。
/// 解析与取值全走 lib；子命令动作只把结果填进 StartupOptions——真正的模式分发在
/// App.OnStartup。GUI 进程无控制台，lib 的 help/报因控制台输出不可见，统一由
/// ShowUsage/ShowError 弹框收场。</summary>
public static class Cli
{
    private const string Caption = "WindowMerger";

    /// <summary>用法摘要（帮助弹窗与报因弹窗共用；lib 生成的控制台帮助在 GUI 下不可见）。</summary>
    public const string UsageText = """
        用法:
          WindowMerger                    合并宿主 + 托盘常驻（「启动到托盘」勾选决定是否弹主窗）
          WindowMerger detect             检测一次 snap 布局，输出一行 JSON 后退出（调试/CI）

        说明:
          吸附交互 = 把窗口拖进宿主空格，或点空格上的「选择窗口」按钮；
          snap 布局接管 = 托盘热键 Ctrl+Alt+M（接管宿主与主窗口同进程，每屏一扇）。

        示例:
          WindowMerger
          WindowMerger detect
        """;

    public static CliParseResult Parse(string[] args)
    {
        var opts = new StartupOptions();

        var detectCmd = new Command("detect", "检测一次 snap 布局，输出一行 JSON 后退出");
        detectCmd.SetAction(_ => { opts.Mode = LaunchMode.Detect; return 0; });

        var root = new RootCommand("把任意独立窗口合并进同一个带边框宿主窗口（无参 = 合并宿主 + 托盘常驻）");
        root.Subcommands.Add(detectCmd);
        root.SetAction(_ => { opts.Mode = LaunchMode.Combined; return 0; });

        var parseResult = root.Parse(args);
        if (parseResult.Errors is { Count: > 0 } parseErrors)
        {
            return new CliParseResult(null, parseErrors.Select(e => e.Message).ToArray(), Help: false);
        }
        parseResult.Invoke();
        // lib 内建 help（--help/-h）命中时不执行任何动作：控制台输出在 GUI 下不可见，
        // 报给调用方弹用法框（退出码 0）
        if (opts.Mode == LaunchMode.None)
        {
            return new CliParseResult(null, Array.Empty<string>(), Help: true);
        }
        return new CliParseResult(opts, Array.Empty<string>(), Help: false);
    }

    /// <summary>请求用法（--help）：弹用法框，进程正常退出（ExitCode 由调用方保持 0）。</summary>
    public static void ShowUsage()
        => MessageBox.Show(UsageText, Caption, MessageBoxButton.OK, MessageBoxImage.Information);

    /// <summary>解析失败：中文报因（常见 lib 报因映射，未知回落原文）+ 用法，调用方以退出码 1 结束。</summary>
    public static void ShowError(IReadOnlyList<string> errors)
    {
        string detail = string.Join("\n", errors.Select(MapError));
        MessageBox.Show(detail + "\n\n" + UsageText, Caption, MessageBoxButton.OK, MessageBoxImage.Warning);
    }

    private static string MapError(string message)
    {
        // lib 报因为英文；按前缀映射成中文，令牌取首个单引号段（无则省略）
        string token = ExtractQuoted(message);
        string suffix = token.Length > 0 ? $"“{token}”" : "";
        if (message.StartsWith("Unrecognized command or argument"))
            return $"无法识别的参数或命令 {suffix}";
        if (message.Contains("requires an argument") || message.Contains("Missing value")
            || message.Contains("is missing") || message.Contains("Missing required"))
            return $"参数缺少值 {suffix}";
        if (message.Contains("already defined"))
            return $"参数重复 {suffix}";
        return message;
    }

    private static string ExtractQuoted(string message)
    {
        int open = message.IndexOf('\'');
        if (open < 0) return "";
        int close = message.IndexOf('\'', open + 1);
        return close > open ? message[(open + 1)..close] : "";
    }
}
