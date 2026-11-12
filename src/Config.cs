using System.IO;
using System.Text.Json;

namespace WindowMerger;

public sealed class AppConfig
{
    public double Ratio { get; set; } = 0.5;
    public string Theme { get; set; } = "Auto";
    public bool CheckUpdates { get; set; } = true; // 启动自动检查更新（GitHub Release）
    public List<long>? AttachedPids { get; set; }
    public List<long>? AttachedHwnds { get; set; }
    // 窗口几何 = 正常态矩形（物理像素，存时乘窗口所在屏 DPI）+ 是否最大化；启动恢复时
    // 按目标屏 DPI 换算回 DIP 并钳制到可见显示器工作区（防跨 DPI 漂移/屏外幽灵窗）。
    // 旧版 Width/Height 字段不再读取（JSON 反序列化自动忽略多余属性）
    public double? WinLeft { get; set; }
    public double? WinTop { get; set; }
    public double? WinRight { get; set; }
    public double? WinBottom { get; set; }
    public bool WinMaximized { get; set; }
}

public static class ConfigStore
{
    private static readonly string DirPath =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "WindowMerger");

    private static string FilePath = Path.Combine(DirPath, "config.json");

    private static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

    /// <summary>
    /// 实例隔离（snap 接管 / 多实例）：带 --profile &lt;name&gt; 的实例改用 config-&lt;name&gt;.json，
    /// 多实例互不覆盖对方的孤儿救援记录（AttachedHwnds）与几何。必须在首次 Load/Save 之前
    /// 调用（App.OnStartup 开头）；不调用或名字清洗后为空 = 默认 config.json（行为不变）。
    /// profile 名只保留字母/数字/连字符（防路径拼接注入），截断到 32 字符。
    /// </summary>
    public static void Configure(string? profile)
    {
        if (string.IsNullOrWhiteSpace(profile)) return;
        string safe = new string(profile.Where(c => char.IsAsciiLetterOrDigit(c) || c == '-').Take(32).ToArray());
        if (safe.Length == 0) return;
        FilePath = Path.Combine(DirPath, $"config-{safe}.json");
    }

    /// <summary>当前实例的配置文件路径（测试用 / 报因文案用）。</summary>
    public static string FilePathForDiagnostics => FilePath;

    public static AppConfig Load()
    {
        try
        {
            if (File.Exists(FilePath))
            {
                return JsonSerializer.Deserialize<AppConfig>(File.ReadAllText(FilePath), JsonOpts) ?? new AppConfig();
            }
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException)
        {
            // 配置损坏不应阻断启动，回退默认值
        }
        return new AppConfig();
    }

    public static void Save(AppConfig config)
    {
        Directory.CreateDirectory(DirPath);
        File.WriteAllText(FilePath, JsonSerializer.Serialize(config, JsonOpts));
    }
}
