using System.Windows.Media;
using Microsoft.Win32;

namespace WindowMerger;

internal enum AppThemeMode
{
    Auto,
    Light,
    Dark,
}

/// <summary>
/// 亮暗主题：Auto 跟随 Windows 应用主题（注册表 AppsUseLightTheme），Light/Dark 手动指定。
/// HostWindow 在 WM_SETTINGCHANGE(ImmersiveColorSet) 且 Mode==Auto 时自动刷新。
/// 注意：类名不能用 Theme/ThemeMode——.NET 10 WPF 的 Window 基类自带实验性 ThemeMode 属性，会遮蔽。
/// </summary>
internal static class AppTheme
{
    public sealed record Palette(
        Color Bar,
        Color Border,
        Color Divider,
        Color DividerHover,
        Color Text,
        Color ButtonHover,
        Color DangerHover);

    private static readonly Palette DarkP = new(
        Bar: Color.FromRgb(0x20, 0x20, 0x20),
        Border: Color.FromRgb(0x3A, 0x3A, 0x3A),
        Divider: Color.FromRgb(0x3C, 0x3C, 0x3C),
        DividerHover: Color.FromRgb(0x2B, 0x5B, 0x8F),
        Text: Color.FromRgb(0xD8, 0xD8, 0xD8),
        ButtonHover: Color.FromRgb(0x3C, 0x3C, 0x3C),
        DangerHover: Color.FromRgb(0xC4, 0x2B, 0x1C));

    private static readonly Palette LightP = new(
        Bar: Color.FromRgb(0xF3, 0xF3, 0xF3),
        Border: Color.FromRgb(0xC0, 0xC0, 0xC0),
        Divider: Color.FromRgb(0xC0, 0xC0, 0xC0),
        DividerHover: Color.FromRgb(0xA9, 0xC7, 0xE8),
        Text: Color.FromRgb(0x1F, 0x1F, 0x1F),
        ButtonHover: Color.FromRgb(0xDC, 0xDC, 0xDC),
        DangerHover: Color.FromRgb(0xD1, 0x34, 0x38));

    public static AppThemeMode Mode { get; set; } = AppThemeMode.Auto;

    public static bool IsDarkNow => Mode switch
    {
        AppThemeMode.Dark => true,
        AppThemeMode.Light => false,
        _ => ReadSystemDark(),
    };

    public static Palette Current() => IsDarkNow ? DarkP : LightP;

    public static SolidColorBrush Brush(Color c)
    {
        var b = new SolidColorBrush(c);
        b.Freeze();
        return b;
    }

    private static bool ReadSystemDark()
    {
        var v = Registry.GetValue(
            @"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            "AppsUseLightTheme", 1);
        return v is int i ? i == 0 : true;
    }
}
