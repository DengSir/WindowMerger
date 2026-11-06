# ASCII-only: capture current window and run the same edge scan as baseline.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTCM { public int L, T, R, B; }
public static class CM {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTCM r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
}
"@
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$h = [IntPtr]$proc.MainWindowHandle
$r = New-Object RECTCM
[CM]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $ht = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [CM]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
$g.Dispose()
Write-Output ("PRINTWINDOW_OK=" + $ok + " SIZE=" + $w + "x" + $ht)
$bmp.Save("$env:TEMP\wm_current_full.png")

$my = [int]($ht / 2); $mx = [int]($w / 2)
$l = ""; $r2 = ""; $t = ""; $b = ""
for ($x = 0; $x -lt 8; $x++) { $c = $bmp.GetPixel($x, $my); $l += ("{0,4}" -f $c.R) }
for ($x = 1; $x -le 8; $x++) { $c = $bmp.GetPixel($w - $x, $my); $r2 += ("{0,4}" -f $c.R) }
for ($y = 0; $y -lt 8; $y++) { $c = $bmp.GetPixel($mx, $y); $t += ("{0,4}" -f $c.R) }
for ($y = 1; $y -le 8; $y++) { $c = $bmp.GetPixel($mx, $ht - $y); $b += ("{0,4}" -f $c.R) }
Write-Output ("LEFT  x0..7 :{0}" -f $l)
Write-Output ("RIGHT x-1..-8:{0}" -f $r2)
Write-Output ("TOP   y0..7 :{0}" -f $t)
Write-Output ("BOT   y-1..-8:{0}" -f $b)
$bmp.Dispose()
Write-Output CURRENT_EDGE_DONE
