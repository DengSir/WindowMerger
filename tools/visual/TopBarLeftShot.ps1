# ASCII-only: capture left side of top bar (icon + label) via PrintWindow.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTTL { public int L, T, R, B; }
public static class TL {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTTL r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
}
"@
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$h = [IntPtr]$proc.MainWindowHandle
$r = New-Object RECTTL
[TL]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap(($r.R - $r.L), ($r.B - $r.T))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [TL]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
$g.Dispose()
Write-Output ("PRINTWINDOW_OK=" + $ok)
$strip = $bmp.Clone([System.Drawing.Rectangle]::new(0, 0, 300, 30), $bmp.PixelFormat)
$zoom = New-Object System.Drawing.Bitmap(900, 90)
$gz = [System.Drawing.Graphics]::FromImage($zoom)
$gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$gz.DrawImage($strip, 0, 0, 900, 90)
$gz.Dispose()
$zoom.Save("$env:TEMP\wm_topbar_left.png")
$zoom.Dispose()
$strip.Dispose()
$bmp.Dispose()
Write-Output LEFT_SHOT_DONE
