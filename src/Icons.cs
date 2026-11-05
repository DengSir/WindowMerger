using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Media;

namespace WindowMerger;

/// <summary>
/// Font Awesome Free 双字体加载与图标码位。
/// Solid（fa-solid-900.ttf）：菜单图标、分隔条把手、关闭 ✕；
/// Regular（fa-regular-400.ttf）：最大化/还原按钮的空心方块与空心 clone。
/// 字体以 WPF Resource 内嵌进程序集，FontFamily 必须在 App.xaml 里以
/// "pack://application:,,,/assets/<文件>#<完整家族名>" 声明（XAML 类型转换器路径）。
/// 实测坑（.NET 10 WPF）：代码里 new FontFamily(同样的 pack 字符串) 能构造、
/// GetResourceStream/Fonts.GetFontFamilies 也正常，但 DWrite 渲染不解析——
/// 全部回退缺字；只有 XAML 声明的实例渲染正常。
/// 校验用渲染宽度对比（探针码位 vs 确定缺失的私用区码位）——GlyphTypeface/
/// TryGetGlyphTypeface/GetTypefaces 对 pack 字体均不可用。失败回退 Unicode 字形，
/// 失败结果一并缓存，避免每次访问重复解析。
/// </summary>
internal static class Icons
{
    // FontFamily 解析用完整名（ID-1 家族名 "Font Awesome 6 Free" 反而解析不到）
    private const string FamilyNameSolid = "Font Awesome 6 Free Solid";
    private const string FamilyNameRegular = "Font Awesome 6 Free Regular";

    private static FontFamily? _solid;
    private static bool _solidTried;
    private static FontFamily? _regular;
    private static bool _regularTried;

    /// <summary>Solid 字体（主字体）。</summary>
    public static FontFamily? Family
        => Ensure(ref _solid, ref _solidTried, "FaSolid", FamilyNameSolid, 0xF00D);

    /// <summary>Regular 字体（空心风格）。</summary>
    public static FontFamily? FamilyRegular
        => Ensure(ref _regular, ref _regularTried, "FaRegular", FamilyNameRegular, 0xF096);

    private static FontFamily? Ensure(ref FontFamily? cache, ref bool tried, string resourceKey, string familyName, int probeCodepoint)
    {
        if (!tried)
        {
            cache = TryLoad(resourceKey, familyName, probeCodepoint);
            tried = true;
        }
        return cache;
    }

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

    // 顶条功能按钮图标（Solid 集）
    public static string? PickLeft  => Family != null ? "\uF060" : null; // arrow-left
    public static string? PickRight => Family != null ? "\uF061" : null; // arrow-right
    public static string? Swap      => Family != null ? "\uF0EC" : null; // right-left
    public static string? Release   => Family != null ? "\uF127" : null; // unlink

    // 分隔条把手
    public static string? Grip => Family != null ? "\uF338" : null; // grip-lines-vertical

    private static FontFamily? TryLoad(string resourceKey, string familyName, int probeCodepoint)
    {
        try
        {
            var f = Application.Current?.TryFindResource(resourceKey) as FontFamily;
            if (f == null) return null;

            // 渲染宽度对比：家族真实包含探针码位时，与确定缺失的私用区码位宽度不同
            double wp = MeasureGlyph(f, probeCodepoint);
            double wm = MeasureGlyph(f, 0xF8FF); // FA 不包含的私用区码位（必为缺字回退）
            if (wp > 0 && Math.Abs(wp - wm) > 0.01)
            {
                return f;
            }
        }
        catch (Exception e) when (e is System.IO.FileFormatException or UriFormatException)
        {
            // 资源缺失/损坏按设计降级为 Unicode 字形
        }
        return null;
    }

    private static double MeasureGlyph(FontFamily f, int codepoint)
    {
        var ft = new FormattedText(
            ((char)codepoint).ToString(),
            CultureInfo.InvariantCulture,
            FlowDirection.LeftToRight,
            new Typeface(f, FontStyles.Normal, FontWeights.Normal, FontStretches.Normal),
            16,
            Brushes.Black,
            null,
            TextFormattingMode.Ideal,
            1.0);
        return ft.Width;
    }
}
