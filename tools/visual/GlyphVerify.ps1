# ASCII-only: verify FA glyphs render from embedded fonts (PrintWindow, z-order immune).
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTP2 { public int L, T, R, B; }
public static class PW3 {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTP2 r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
"@
[PW3]::SetProcessDPIAware() | Out-Null

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
$hr = New-Object RECTP2
[PW3]::GetWindowRect($hm, [ref]$hr) | Out-Null
$bmp = New-Object System.Drawing.Bitmap(($hr.R - $hr.L), ($hr.B - $hr.T))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [PW3]::PrintWindow($hm, $hdc, 2)
$g.ReleaseHdc($hdc)
$g.Dispose()
Write-Output ("PRINTWINDOW_OK=" + $ok)
# top bar right side: caption buttons area
$strip = $bmp.Clone([System.Drawing.Rectangle]::new(($hr.R - $hr.L) - 340, 0, 340, 30), $bmp.PixelFormat)
$zoom = New-Object System.Drawing.Bitmap(1020, 90)
$gz = [System.Drawing.Graphics]::FromImage($zoom)
$gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$gz.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$gz.DrawImage($strip, 0, 0, 1020, 90)
$gz.Dispose()
$zoom.Save("$env:TEMP\wm_captionbtns.png")
$zoom.Dispose()
$strip.Dispose()
$bmp.Dispose()
Write-Output GLYPH_SHOT_DONE
