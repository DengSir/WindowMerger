param(
    [Parameter(Mandatory = $true)][string]$Path,
    [int]$X = -1,
    [int]$Y = -1,
    [int]$W = -1,
    [int]$H = -1
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class DpiHelper {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
    public struct RECT { public int Left, Top, Right, Bottom; }
    public struct POINT { public int X, Y; }
}
"@
[DpiHelper]::SetProcessDPIAware() | Out-Null

if ($X -lt 0) {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $X = $bounds.X; $Y = $bounds.Y; $W = $bounds.Width; $H = $bounds.Height
}

$bmp = New-Object System.Drawing.Bitmap($W, $H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($X, $Y, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "SHOT_OK $Path ($X,$Y,$W,$H)"
