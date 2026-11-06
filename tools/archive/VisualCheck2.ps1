# ASCII-only: capture the host's own render via PrintWindow (immune to z-order).
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTP { public int L, T, R, B; }
public static class PW2 {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTP r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
"@
[PW2]::SetProcessDPIAware() | Out-Null

Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:APPDATA\WindowMerger\config.json" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "visual-3"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 700
Start-Process mspaint
Start-Sleep -Milliseconds 1400
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
$hr = New-Object RECTP
[PW2]::GetWindowRect($hm, [ref]$hr) | Out-Null
$w = $hr.R - $hr.L; $h = $hr.B - $hr.T
Write-Output ("HOST {0}x{1} at ({2},{3})" -f $w, $h, $hr.L, $hr.T)

$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [PW2]::PrintWindow($hm, $hdc, 2)   # PW_RENDERFULLCONTENT
$g.ReleaseHdc($hdc)
$g.Dispose()
Write-Output ("PRINTWINDOW_OK=" + $ok)

# top bar strip (label + status + border below it)
$strip = $bmp.Clone([System.Drawing.Rectangle]::new(0, 0, 560, 44), $bmp.PixelFormat)
$strip.Save("$env:TEMP\wm_topbar.png")
$strip.Dispose()
# top-left corner zoom x8 (1px border check)
$corner = $bmp.Clone([System.Drawing.Rectangle]::new(0, 0, 12, 12), $bmp.PixelFormat)
$zoom = New-Object System.Drawing.Bitmap(96, 96)
$gz = [System.Drawing.Graphics]::FromImage($zoom)
$gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$gz.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$gz.DrawImage($corner, 0, 0, 96, 96)
$gz.Dispose()
$zoom.Save("$env:TEMP\wm_corner.png")
$zoom.Dispose()
$corner.Dispose()
$bmp.Dispose()
Write-Output "SHOT_OK"

$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p2 in $wm) { $null = $p2.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output VISUAL_CHECK3_DONE
