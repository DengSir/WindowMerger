using System.IO;
using System.Linq;
using System.Windows.Media;

namespace WindowMerger;

/// <summary>
/// Font Awesome Free 双字体加载与图标码位。
/// Solid（fa-solid-900.ttf）：菜单图标、分隔条把手、关闭 ✕；
/// Regular（fa-regular-400.ttf）：最大化/还原按钮的空心方块与空心 clone。
/// 字体以 Content 随 exe 分发；pack:// 资源流在本应用内会静默解析失败
/// （GetResourceStream 返回 null），因此直接用文件路径加载并用字形自验证兜底。
/// </summary>
internal static class Icons
{
    // FontFamily 解析用完整名（ID-1 家族名 "Font Awesome 6 Free" 反而解析不到）
    private const string FamilyNameSolid = "Font Awesome 6 Free Solid";
    private const string FamilyNameRegular = "Font Awesome 6 Free Regular";

    private static FontFamily? _solid;
    private static FontFamily? _regular;

    /// <summary>Solid 字体（主字体）。</summary>
    public static FontFamily? Family => _solid ??= TryLoad("fa-solid-900.ttf", FamilyNameSolid, 0xF00D);

    /// <summary>Regular 字体（空心风格）。</summary>
    public static FontFamily? FamilyRegular => _regular ??= TryLoad("fa-regular-400.ttf", FamilyNameRegular, 0xF096);

    // 窗口控制按钮（字体不可用时回退原 Unicode 字形）
    public static string Minimize => Family != null ? "\uF068" : "\u2500"; // minus（Solid）
    public static string Maximize => FamilyRegular != null || Family != null ? "\uF096" : "\u25A1"; // square 空心（Regular）
    public static string Restore  => FamilyRegular != null || Family != null ? "\uF24D" : "\u25A1"; // clone 空心（Regular）
    public static string Close    => Family != null ? "\uF00D" : "\u2715"; // xmark（Solid）

    /// <summary>侧格已吸附时，左右按钮翻转为"释放该侧"（window-restore：窗口飞回原位）。</summary>
    public static string ReleasePane => Family != null ? "\uF2D2" : "\u2715";

    /// <summary>最大化/还原图标用 Regular 空心字体。</summary>
    public static FontFamily? MaximizeFont => FamilyRegular ?? Family;
    public static FontFamily? RestoreFont => FamilyRegular ?? Family;

    // 菜单项图标（Solid 集）
    public static string? PickLeft  => Family != null ? "\uF060" : null; // arrow-left
    public static string? PickRight => Family != null ? "\uF061" : null; // arrow-right
    public static string? Swap      => Family != null ? "\uF0EC" : null; // right-left
    public static string? Release   => Family != null ? "\uF127" : null; // unlink
    public static string? Exit      => Family != null ? "\uF011" : null; // power-off

    // 分隔条把手
    public static string? Grip => Family != null ? "\uF338" : null; // grip-lines-vertical

    private static FontFamily? TryLoad(string fileName, string familyName, int probeCodepoint)
    {
        try
        {
            string path = Path.Combine(AppContext.BaseDirectory, "Resources", fileName);
            if (!File.Exists(path)) return null;

            var f = new FontFamily(path + "#" + familyName);
            // 必须真解析出 FA 字形才算可用
            if (f.GetTypefaces().FirstOrDefault()?.TryGetGlyphTypeface(out var gtf) != true
                || !gtf.CharacterToGlyphMap.ContainsKey(probeCodepoint))
            {
                return null;
            }
            return f;
        }
        catch (Exception e) when (e is IOException or FileNotFoundException or FileFormatException)
        {
            return null;
        }
    }
}
