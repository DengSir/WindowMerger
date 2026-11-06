# ASCII-only: capture right side of top bar (caption buttons) via PrintWindow.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTSB { public int L, T, R, B; }
public static class SB {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTSB r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
}
"@
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$h = [IntPtr]$proc.MainWindowHandle
$r = New-Object RECTSB
[SB]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L
$bmp = New-Object System.Drawing.Bitmap($w, ($r.B - $r.T))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[SB]::PrintWindow($h, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc)
$g.Dispose()
$strip = $bmp.Clone([System.Drawing.Rectangle]::new($w - 340, 0, 340, 30), $bmp.PixelFormat)
$zoom = New-Object System.Drawing.Bitmap(680, 60)
$gz = [System.Drawing.Graphics]::FromImage($zoom)
$gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$gz.DrawImage($strip, 0, 0, 680, 60)
$gz.Dispose()
$zoom.Save("$env:TEMP\wm_sidebtns.png")
$zoom.Dispose()
$strip.Dispose()
$bmp.Dispose()
Write-Output SIDE_SHOT_DONE
