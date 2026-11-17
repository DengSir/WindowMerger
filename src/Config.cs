using System.IO;
using System.Text.Json;

namespace WindowMerger;

public sealed class AppConfig
{
    public double Ratio { get; set; } = 0.5;
    // 布局种类（PaneLayoutDef.ConfigName：LR/LCR/LTR/Quad）与次比例（含义随布局）；
    // 非法 Layout 由宿主回退 LR
    public string Layout { get; set; } = "LR";
    public double Ratio2 { get; set; } = 0.5;
    public string Theme { get; set; } = "Auto";
    public bool CheckUpdates { get; set; } = true; // 启动自动检查更新（GitHub Release）
    public bool StartToTray { get; set; } // 勾选 = 无参启动不弹主窗，仅托盘常驻（托盘菜单可切）
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

    private static readonly string FilePath = Path.Combine(DirPath, "config.json");

    private static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

    /// <summary>当前实例的配置文件路径（测试 / 报因文案用）。单进程多宿主后无 profile 概念
    /// （config-&lt;名&gt;.json 实例隔离已随 merge 子命令退役，2026-11-18）。</summary>
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
