param(
    [Parameter(Mandatory = $true)][string]$ShotPath
)

# ASCII-only: PowerShell 5.1 reads UTF-8-no-BOM as ANSI and Chinese text breaks parsing.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinAtomic {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    public struct POINT { public int X, Y; }
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[WinAtomic]::SetProcessDPIAware() | Out-Null

$proc = Get-Process WindowMerger -ErrorAction Stop
$h = $proc.MainWindowHandle
if ($h -eq [IntPtr]::Zero) { Write-Output "NO_WINDOW"; exit 1 }

[WinAtomic]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x0003) | Out-Null   # TOPMOST
[WinAtomic]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 500

$topmost = (([WinAtomic]::GetWindowLong($h, -20) -band 0x8) -ne 0)
$fg = [WinAtomic]::GetForegroundWindow() -eq $h
$r = New-Object WinAtomic+RECT
[WinAtomic]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output ("TOPMOST={0} FOREGROUND={1} RECT=({2},{3},{4},{5})" -f $topmost, $fg, $r.Left, $r.Top, $r.Right, $r.Bottom)

$p1 = New-Object WinAtomic+POINT
$p1.X = $r.Left + 60; $p1.Y = $r.Top + 14   # top bar
$h1 = [WinAtomic]::WindowFromPoint($p1)
Write-Output ("HIT_TOPBAR=0x{0:X} IS_HOST={1}" -f $h1.ToInt64(), ($h1 -eq $h))

$p2 = New-Object WinAtomic+POINT
$p2.X = [int](($r.Left + $r.Right) / 2); $p2.Y = [int](($r.Top + $r.Bottom) / 2)   # center hole
$h2 = [WinAtomic]::WindowFromPoint($p2)
Write-Output ("HIT_CENTER=0x{0:X} IS_HOST={1} (expect False = click-through)" -f $h2.ToInt64(), ($h2 -eq $h))

$p3 = New-Object WinAtomic+POINT
$p3.X = $r.Left + 1; $p3.Y = [int](($r.Top + $r.Bottom) / 2)   # left border
$h3 = [WinAtomic]::WindowFromPoint($p3)
Write-Output ("HIT_LEFTBORDER=0x{0:X} IS_HOST={1}" -f $h3.ToInt64(), ($h3 -eq $h))

$w = $r.Right - $r.Left; $ht = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($ShotPath, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()

# 截完立即还原普通层级，不污染用户正在跑的实例
[WinAtomic]::SetWindowPos($h, [IntPtr](-2), 0, 0, 0, 0, 0x0003) | Out-Null   # HWND_NOTOPMOST
Write-Output "SHOT_OK $ShotPath (topmost restored)"
