using System.CommandLine;
using System.CommandLine.Parsing;
using System.Globalization;
using System.Windows;

namespace WindowMerger;

/// <summary>启动模式（命令式子命令）：Cli.Parse 时由命中的子命令动作填写。None = 无命令
/// 动作命中（lib 已按内建 help 处理，GUI 下由 ShowUsage 弹框收场）。</summary>
public enum LaunchMode
{
    None,
    /// <summary>无参启动：托盘常驻 + 按「启动到托盘」勾选决定是否弹默认主窗。</summary>
    Combined,
    /// <summary>只托盘：常驻监听 Ctrl+Alt+M，不开主窗。</summary>
    Tray,
    /// <summary>检测一次 snap 布局，stdout 输出一行 JSON 后退出。</summary>
    Detect,
    /// <summary>吸附两个独立窗口进宿主（显式子命令；无参 Combined 在 App 内走独立分发）。</summary>
    Merge,
}

/// <summary>启动参数（命令式 CLI 解析产物）：宿主模式目标、snap 接管直连句柄、实例隔离
/// profile。</summary>
public sealed record StartupOptions
{
    public LaunchMode Mode { get; set; } = LaunchMode.None;
    public string? Left { get; set; }
    public string? Right { get; set; }
    // 第 3/4 格目标（位置参数专属，按布局格序填入；--left/--right = 前 2 格的命名别名）
    public string? Pane2 { get; set; }
    public string? Pane3 { get; set; }
    public string? LeftExe { get; set; }
    public string? RightExe { get; set; }
    public long? LeftHwnd { get; set; }
    public long? RightHwnd { get; set; }
    public string? Profile { get; set; }
    // snap 接管落位（两窗口可见边界并集，物理 px + 左右比例）：由 merge 的句柄参数派生
    public ((double X, double Y, double W, double H) Rect, double Ratio)? Snap { get; set; }
    // 单实例唤起开新扇的级联偏移（DIP，按存活宿主扇数阶梯）：仅无参唤起路径由 App 填写，
    // CLI 解析不产生该值——多扇平级宿主同几何会完全重叠，偏移让新扇可见
    public double CascadeDip { get; set; }
}

/// <summary>Cli.Parse 结果：Help = 请求了用法（--help，动作未执行）；Errors 非空 = 解析
/// 失败；两者皆空时 Options 必非 null（Mode 已由命中的子命令动作填写）。</summary>
public sealed record CliParseResult(StartupOptions? Options, string[] Errors, bool Help);

/// <summary>命令式 CLI（System.CommandLine）：根命令无参 = 组合模式，子命令 tray / detect /
/// merge [左] [右]。解析与取值全走 lib；子命令动作只把结果填进 StartupOptions——真正的
/// 模式分发在 App.OnStartup。GUI 进程无控制台，lib 的 help/报因控制台输出不可见，统一由
/// ShowUsage/ShowError 弹框收场。</summary>
public static class Cli
{
    private const string Caption = "WindowMerger";

    /// <summary>用法摘要（帮助弹窗与报因弹窗共用；lib 生成的控制台帮助在 GUI 下不可见）。</summary>
    public const string UsageText = """
        用法:
          WindowMerger                    合并宿主 + 托盘常驻（「启动到托盘」勾选决定是否弹主窗）
          WindowMerger tray               托盘常驻：Ctrl+Alt+M 捕捉 snap 布局
          WindowMerger detect             检测一次 snap 布局，输出一行 JSON 后退出
          WindowMerger merge [格1] [格2] [格3] [格4]
                                          吸附独立窗口（位置参数按布局格序填入）

        merge 选项:
          --left <名|PID> / --right <名|PID>    前 2 格吸附目标（别名 -l / -r）
          --left-exe / --right-exe <完整路径>   前 2 格目标 exe 不存在时按路径拉起
          --left-hwnd / --right-hwnd <句柄>     snap 接管直连（十进制或 0x 十六进制）
          --profile <名>                        实例隔离（config-<名>.json）

        示例:
          WindowMerger merge notepad mspaint
          WindowMerger merge --left Code --right ZCode
          WindowMerger merge --left-hwnd 123456 --right-hwnd 123458 --profile snap-0
        """;

    public static CliParseResult Parse(string[] args)
    {
        var opts = new StartupOptions();

        var leftOption = new Option<string?>("--left", "-l") { Description = "左侧目标：进程名或 PID" };
        var rightOption = new Option<string?>("--right", "-r") { Description = "右侧目标：进程名或 PID" };
        var leftExeOption = new Option<string?>("--left-exe") { Description = "左侧目标 exe 完整路径（不存在时拉起）" };
        var rightExeOption = new Option<string?>("--right-exe") { Description = "右侧目标 exe 完整路径（不存在时拉起）" };
        var leftHwndOption = new Option<string?>("--left-hwnd") { Description = "snap 接管直连：左侧顶层窗口句柄" };
        var rightHwndOption = new Option<string?>("--right-hwnd") { Description = "snap 接管直连：右侧顶层窗口句柄" };
        var profileOption = new Option<string?>("--profile") { Description = "实例隔离 profile（config-<名>.json）" };

        // 位置参数必须有默认值才是可选（无默认 = required），arity 显式 ZeroOrOne 兜底；
        // 自定义解析器拒绝 "-" 起头的 token——lib 默认把未知 token 静默落进位置参数，
        // 与「未知旗标报因退出」语义冲突（cli_args_test C3 钉死）
        var leftArg = new Argument<string?>("left")
        {
            Description = "第 1 格目标：进程名或 PID",
            DefaultValueFactory = _ => null,
            Arity = ArgumentArity.ZeroOrOne,
            CustomParser = ParsePositional,
        };
        var rightArg = new Argument<string?>("right")
        {
            Description = "第 2 格目标：进程名或 PID",
            DefaultValueFactory = _ => null,
            Arity = ArgumentArity.ZeroOrOne,
            CustomParser = ParsePositional,
        };
        var pane2Arg = new Argument<string?>("pane2")
        {
            Description = "第 3 格目标：进程名或 PID",
            DefaultValueFactory = _ => null,
            Arity = ArgumentArity.ZeroOrOne,
            CustomParser = ParsePositional,
        };
        var pane3Arg = new Argument<string?>("pane3")
        {
            Description = "第 4 格目标：进程名或 PID",
            DefaultValueFactory = _ => null,
            Arity = ArgumentArity.ZeroOrOne,
            CustomParser = ParsePositional,
        };

        var trayCmd = new Command("tray", "托盘常驻：Ctrl+Alt+M 捕捉 snap 布局，不开主窗");
        trayCmd.SetAction(_ => { opts.Mode = LaunchMode.Tray; return 0; });

        var detectCmd = new Command("detect", "检测一次 snap 布局，输出一行 JSON 后退出");
        detectCmd.SetAction(_ => { opts.Mode = LaunchMode.Detect; return 0; });

        var mergeCmd = new Command("merge", "吸附独立窗口进宿主（位置参数按布局格序填入）");
        mergeCmd.Options.Add(leftOption);
        mergeCmd.Options.Add(rightOption);
        mergeCmd.Options.Add(leftExeOption);
        mergeCmd.Options.Add(rightExeOption);
        mergeCmd.Options.Add(leftHwndOption);
        mergeCmd.Options.Add(rightHwndOption);
        mergeCmd.Options.Add(profileOption);
        mergeCmd.Arguments.Add(leftArg);
        mergeCmd.Arguments.Add(rightArg);
        mergeCmd.Arguments.Add(pane2Arg);
        mergeCmd.Arguments.Add(pane3Arg);
        mergeCmd.SetAction(parseResult =>
        {
            opts.Mode = LaunchMode.Merge;
            opts.Left = parseResult.GetValue(leftOption) ?? parseResult.GetValue(leftArg);
            opts.Right = parseResult.GetValue(rightOption) ?? parseResult.GetValue(rightArg);
            opts.Pane2 = parseResult.GetValue(pane2Arg);
            opts.Pane3 = parseResult.GetValue(pane3Arg);
            opts.LeftExe = parseResult.GetValue(leftExeOption);
            opts.RightExe = parseResult.GetValue(rightExeOption);
            opts.LeftHwnd = ParseHwnd(parseResult.GetValue(leftHwndOption));
            opts.RightHwnd = ParseHwnd(parseResult.GetValue(rightHwndOption));
            opts.Profile = parseResult.GetValue(profileOption);
            return 0;
        });

        var root = new RootCommand("把任意独立窗口合并进同一个带边框宿主窗口（无参 = 合并宿主 + 托盘常驻）");
        root.Subcommands.Add(trayCmd);
        root.Subcommands.Add(detectCmd);
        root.Subcommands.Add(mergeCmd);
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

    /// <summary>位置参数自定义解析：显式提供的 token 以 "-" 起头 → 判为无法识别的参数
    /// （报因走 ShowError 弹框路径）。</summary>
    private static string? ParsePositional(ArgumentResult result)
    {
        if (result.Tokens.Count == 0) return null;
        string token = result.Tokens[0].Value;
        if (token.StartsWith("-"))
        {
            result.AddError($"无法识别的参数或命令 “{token}”");
            return null;
        }
        return token;
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

    /// <summary>句柄字面量：十进制或 0x 十六进制；解析失败返回 null（宿主状态栏报因路径，
    /// 与旧手写解析同语义——句柄垃圾值不算 CLI 解析失败）。</summary>
    private static long? ParseHwnd(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        raw = raw.Trim();
        if (raw.StartsWith("0x", StringComparison.OrdinalIgnoreCase))
        {
            return long.TryParse(raw[2..], NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var h) ? h : null;
        }
        return long.TryParse(raw, out var d) ? d : null;
    }
}
