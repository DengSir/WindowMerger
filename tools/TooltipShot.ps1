# ASCII-only: tooltip theme check - hover the theme button with tooltip forced
# Dark then Light, screen-capture (tooltip is a separate popup window, so
# PrintWindow of the host cannot see it), print sampled RGB pixels for
# deterministic verification, save 3x zoom crops, restore NOTOPMOST + close.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTT { public int L, T, R, B; }
public static class TT {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTT r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
[TT]::SetProcessDPIAware() | Out-Null

$cfgPath = "$env:APPDATA\WindowMerger\config.json"
$c = Get-Content $cfgPath -Raw | ConvertFrom-Json
$c.Ratio = 0.5
$c | ConvertTo-Json | Set-Content $cfgPath

$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"

function Zoom3x([System.Drawing.Bitmap]$src, [System.Drawing.Rectangle]$rc, [string]$path) {
    $crop = $src.Clone($rc, $src.PixelFormat)
    $zw = [int]$crop.Width * 3
    $zh = [int]$crop.Height * 3
    $zoom = New-Object System.Drawing.Bitmap -ArgumentList $zw, $zh
    $zg = [System.Drawing.Graphics]::FromImage($zoom)
    $zg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $zg.DrawImage($crop, 0, 0, $zw, $zh)
    $zg.Dispose()
    $zoom.Save($path)
    $zoom.Dispose()
    $crop.Dispose()
}

foreach ($theme in @("Dark", "Light")) {
    $c = Get-Content $cfgPath -Raw | ConvertFrom-Json
    $c.Theme = $theme
    $c | ConvertTo-Json | Set-Content $cfgPath

    Start-Process $exe
    Start-Sleep -Seconds 3
    $proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST_$theme"; continue }
    $hm = [IntPtr]$proc.MainWindowHandle
    $hr = New-Object RECTT
    [TT]::GetWindowRect($hm, [ref]$hr) | Out-Null

    # topmost so hover reaches the host (restored at the end)
    $null = [TT]::SetWindowPos($hm, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
    Start-Sleep -Milliseconds 400

    # theme button center: [left][right][swap][release][theme]|separator| [min][max][close]
    $bx = $hr.R - 140
    $by = $hr.T + 16
    [TT]::SetCursorPos($bx, $by) | Out-Null
    Start-Sleep -Milliseconds 1200   # tooltip initial delay + fade-in

    $capW = 340; $capH = 90
    $capX = $bx - 80; $capY = $hr.T
    $big = New-Object System.Drawing.Bitmap(2560, 1440)
    $g = [System.Drawing.Graphics]::FromImage($big)
    $g.CopyFromScreen(0, 0, 0, 0, $big.Size)
    $g.Dispose()

    # deterministic color samples: top bar (clean area above the text) + tooltip
    # interior grid (between/around the text glyphs; the modal value = tooltip bg)
    $barPix = $big.GetPixel($hr.L + 60, $hr.T + 5)
    Write-Output ("BAR_{0} rgb({1},{2},{3})" -f $theme, $barPix.R, $barPix.G, $barPix.B)
    foreach ($dy in @(40, 46, 52)) {
        foreach ($dx in @(0, 20, 60, 100, 140)) {
            $p = $big.GetPixel($bx + $dx, $hr.T + $dy)
            Write-Output ("TIP_{0} d({1},{2}) rgb({3},{4},{5})" -f $theme, $dx, $dy, $p.R, $p.G, $p.B)
        }
    }

    Zoom3x $big ([System.Drawing.Rectangle]::new($capX, $capY, $capW, $capH)) "$env:TEMP\wm_tooltip_$theme.png"
    $big.Dispose()
    Write-Output ("SHOT_" + $theme + " at ({0},{1})" -f $capX, $capY)

    # restore NOTOPMOST, close host (graceful), wait for full exit
    $null = [TT]::SetWindowPos($hm, [IntPtr](-2), 0, 0, 0, 0, 0x0003)
    $null = $proc.CloseMainWindow()
    Start-Sleep -Milliseconds 1500
}

# restore user theme setting
$c = Get-Content $cfgPath -Raw | ConvertFrom-Json
$c.Theme = "Auto"
$c | ConvertTo-Json | Set-Content $cfgPath
Write-Output TOOLTIP_SHOT_DONE
