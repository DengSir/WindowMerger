# ASCII-only: hover visual test — cursor over divider / close / max / away,
# PrintWindow strip after each. Theme forced Dark for deterministic colors.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTH { public int L, T, R, B; }
public static class HV {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTH r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
[HV]::SetProcessDPIAware() | Out-Null

# force Dark theme for deterministic expectations (restore Auto at the end)
$cfgPath = "$env:APPDATA\WindowMerger\config.json"
$c = Get-Content $cfgPath -Raw | ConvertFrom-Json
$c.Theme = "Dark"
$c.Ratio = 0.5
$c | ConvertTo-Json | Set-Content $cfgPath

Get-Process WindowMerger -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
$hr = New-Object RECTH
[HV]::GetWindowRect($hm, [ref]$hr) | Out-Null
$w = $hr.R - $hr.L
$null = [HV]::SetWindowPos($hm, [IntPtr](-1), 0, 0, 0, 0, 0x0003)   # topmost so hover reaches us
Start-Sleep -Milliseconds 400

function Snap([string]$tag) {
    Start-Sleep -Milliseconds 400
    $bmp = New-Object System.Drawing.Bitmap($w, ($hr.B - $hr.T))
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    [HV]::PrintWindow($hm, $hdc, 2) | Out-Null
    $g.ReleaseHdc($hdc)
    $g.Dispose()
    $strip = $bmp.Clone([System.Drawing.Rectangle]::new(0, 0, $w, 30), $bmp.PixelFormat)
    $strip.Save("$env:TEMP\wm_hover_$tag.png")
    $strip.Dispose()
    $bmp.Dispose()
    Write-Output ("SHOT_" + $tag)
}

# divider center (ratio 0.5)
$avail = $w - 4 - 8
[HV]::SetCursorPos([int]($hr.L + 2 + $avail * 0.5 + 4), [int](($hr.T + $hr.B) / 2)) | Out-Null
Snap "divider"

# away from window -> base state (divider must NOT stay transparent/highlighted)
[HV]::SetCursorPos(6, 700) | Out-Null
Snap "away"

# max button (normal hover: light gray)
[HV]::SetCursorPos($hr.R - 60, $hr.T + 16) | Out-Null
Snap "max"

# close button (danger hover: red)
[HV]::SetCursorPos($hr.R - 22, $hr.T + 16) | Out-Null
Snap "close"

# away again
[HV]::SetCursorPos(6, 700) | Out-Null
Snap "away2"

$null = [HV]::SetWindowPos($hm, [IntPtr](-2), 0, 0, 0, 0, 0x0003)

# restore user settings
$c = Get-Content $cfgPath -Raw | ConvertFrom-Json
$c.Theme = "Auto"
$c | ConvertTo-Json | Set-Content $cfgPath
Write-Output HOVER_TEST_DONE
