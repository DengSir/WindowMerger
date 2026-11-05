using System.IO;
using System.Text.Json;

namespace WindowMerger;

public sealed class AppConfig
{
    public double Ratio { get; set; } = 0.5;
    public string Theme { get; set; } = "Auto";
    public double? Left { get; set; }
    public double? Top { get; set; }
    public double? Width { get; set; }
    public double? Height { get; set; }
}

public static class ConfigStore
{
    private static readonly string DirPath =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "WindowMerger");

    private static readonly string FilePath = Path.Combine(DirPath, "config.json");

    private static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

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
