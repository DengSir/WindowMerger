# ASCII-only: verify app icon — (1) exe embedded icon, (2) live taskbar icon.
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AV {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[AV]::SetProcessDPIAware() | Out-Null

# 1. exe embedded icon (ApplicationIcon)
$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
$ico = [System.Drawing.Icon]::ExtractAssociatedIcon($exe)
$ico.ToBitmap().Save("$env:TEMP\wm_exeicon.png")
$ico.Dispose()
Write-Output "EXE_ICON_SAVED"

# 2. launch app WITHOUT children -> fallback icon path
Start-Process $exe
Start-Sleep -Seconds 3
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }

# find taskbar button, crop its icon area
$root = [System.Windows.Automation.AutomationElement]::RootElement
$taskbar = $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "Shell_TrayWnd")))
$btn = $null
if ($taskbar -ne $null) {
    $all = $taskbar.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($e in $all) { if ($e.Current.Name -match "WindowMerger") { $btn = $e; break } }
}
if ($btn -eq $null) { Write-Output "NO_TASKBAR_BUTTON"; exit 1 }
$rc = $btn.Current.BoundingRectangle
Write-Output ("TASKBAR_BTN {0}x{1} at ({2},{3})" -f $rc.Width, $rc.Height, $rc.X, $rc.Y)
$big = New-Object System.Drawing.Bitmap(2560, 1440)
$g = [System.Drawing.Graphics]::FromImage($big)
$g.CopyFromScreen(0, 0, 0, 0, $big.Size)
$g.Dispose()
$x = [int]$rc.X; $y = [int]$rc.Y; $w = [int]$rc.Width; $h = [int]$rc.Height
$crop = $big.Clone([System.Drawing.Rectangle]::new($x, $y, $w, $h), $big.PixelFormat)
$zoom = New-Object System.Drawing.Bitmap(160, 160)
$gz = [System.Drawing.Graphics]::FromImage($zoom)
$gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$gz.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$gz.DrawImage($crop, 0, 0, 160, 160)
$gz.Dispose()
$zoom.Save("$env:TEMP\wm_taskbaricon.png")
$zoom.Dispose()
$crop.Dispose()
$big.Dispose()
Write-Output "TASKBAR_ICON_SAVED"

$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm) { $null = $p.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Write-Output ICON_VERIFY_DONE
