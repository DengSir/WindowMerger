param(
    [Parameter(Mandatory = $true)][long]$Hwnd,
    [Parameter(Mandatory = $true)][string]$Path,
    [int]$Height = 70
)

# ASCII-only: read live rect then screenshot its top strip, atomically.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ShotHwnd {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[ShotHwnd]::SetProcessDPIAware() | Out-Null

$r = New-Object ShotHwnd+RECT
[ShotHwnd]::GetWindowRect([IntPtr]$Hwnd, [ref]$r) | Out-Null
$w = $r.Right - $r.Left
$h = [Math]::Min($Height, $r.Bottom - $r.Top)
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ("SHOT_OK {0} RECT=({1},{2},{3},{4})" -f $Path, $r.Left, $r.Top, $r.Right, $r.Bottom)
