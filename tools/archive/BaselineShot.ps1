# ASCII-only: baseline capture — full-window PrintWindow + top bar strips.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTB { public int L, T, R, B; }
public static class BL {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTB r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
}
"@
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$h = [IntPtr]$proc.MainWindowHandle
$r = New-Object RECTB
[BL]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $ht = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [BL]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
$g.Dispose()
Write-Output ("PRINTWINDOW_OK=" + $ok + " SIZE=" + $w + "x" + $ht)
$bmp.Save("$env:TEMP\wm_baseline_full.png")
# top bar left strip (icon + label)
$bmp.Clone([System.Drawing.Rectangle]::new(0, 0, 300, 30), $bmp.PixelFormat).Save("$env:TEMP\wm_baseline_left.png")
# top bar right strip (caption buttons)
$bmp.Clone([System.Drawing.Rectangle]::new($w - 340, 0, 340, 30), $bmp.PixelFormat).Save("$env:TEMP\wm_baseline_right.png")
# pane area sample (divider region)
$bmp.Clone([System.Drawing.Rectangle]::new([int]($w/2) - 60, 40, 120, 120), $bmp.PixelFormat).Save("$env:TEMP\wm_baseline_divider.png")
$bmp.Dispose()
Write-Output BASELINE_DONE
