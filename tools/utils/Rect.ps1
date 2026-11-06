param(
    [long]$Hwnd = 0,
    [string]$Title = ""
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinRect {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[WinRect]::SetProcessDPIAware() | Out-Null

$h = [IntPtr]$Hwnd
if ($h -eq [IntPtr]::Zero -and $Title -ne "") { $h = [WinRect]::FindWindow($null, $Title) }
if ($h -eq [IntPtr]::Zero) { Write-Output "NOT_FOUND"; exit 1 }
if (-not [WinRect]::IsWindow($h)) { Write-Output "NOT_WINDOW"; exit 1 }
$iconic = [WinRect]::IsIconic($h)
$r = New-Object WinRect+RECT
[WinRect]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output ("HWND=0x{0:X} ICONIC={1} RECT=({2},{3},{4},{5}) SIZE={6}x{7}" -f `
    $h.ToInt64(), $iconic, $r.Left, $r.Top, $r.Right, $r.Bottom, ($r.Right - $r.Left), ($r.Bottom - $r.Top))
