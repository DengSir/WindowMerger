# ASCII-only: cross-DPI attach regression — a 96-DPI window (left 100% monitor) attached
# into a host on the 150% 4K primary. Guards the "seam" fix: pane edges must match the
# child's visible frame bounds (DWMWA_EXTENDED_FRAME_BOUNDS) within 1px.
# Asserts left/top/bottom (DPI-independent edges) and right (ratio from config.json).
param(
    [string]$Exe = "D:\Develop\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
)
$ErrorActionPreference = "Continue"
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTT { public int L, T, R, B; }
public static class CT {
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
    [DllImport("user32.dll", SetLastError=true)] public static extern bool EnumWindows(EnumProc cb, IntPtr lp);
    public delegate bool EnumProc(IntPtr h, IntPtr lp);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, uint cmd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTT r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int w, int hh, uint f);
    [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECTT r, int s);
}
"@
[CT]::SetProcessDpiAwarenessContext([IntPtr](-4)) | Out-Null

function Find-TopWindowsOf([int[]]$procIds) {
    $script:found = @()
    $cb = { param($h, $lp)
        $p = 0
        [CT]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
        if ($procIds -contains [int]$p -and [CT]::IsWindowVisible($h) -and [CT]::GetWindow($h, 4) -eq [IntPtr]::Zero) {
            $script:found += $h
        }
        $true
    }
    [CT]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return $script:found
}

# 1. gracefully close running hosts (they hold the exe lock and would fight the test)
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
if ($wm) {
    foreach ($h in (Find-TopWindowsOf $wm.Id)) { [CT]::PostMessageW($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null }
    $wm | Wait-Process -Timeout 6 -ErrorAction SilentlyContinue
}

# 2. spawn mspaint, park it on the LEFT monitor (expected 100%)
$mp = Start-Process mspaint -PassThru
Start-Sleep -Milliseconds 2200
$mph = [IntPtr]::Zero
foreach ($h in (Find-TopWindowsOf @([int]$mp.Id))) { $mph = $h; break }
if ($mph -eq [IntPtr]::Zero) { Write-Output "FAIL_NO_MSPAINT"; exit 1 }
[CT]::SetWindowPos($mph, [IntPtr]::Zero, -2300, 200, 1200, 800, 0x0004) | Out-Null
Start-Sleep -Milliseconds 900
$mpDpi = [CT]::GetDpiForWindow($mph)
if ($mpDpi -ne 96) {
    Stop-Process -Id $mp.Id -Force -ErrorAction SilentlyContinue
    Write-Output ("SKIP_LEFT_MONITOR_NOT_100PCT dpi={0}" -f $mpDpi)
    exit 0
}

# 3. host with CLI attach (pure digits = PID); it opens on the primary 4K
$host_ = Start-Process $Exe -ArgumentList "--left", "$($mp.Id)" -PassThru
Start-Sleep -Milliseconds 3500
$hw = [IntPtr]::Zero
foreach ($h in (Find-TopWindowsOf @([int]$host_.Id))) { $hw = $h; break }
if ($hw -eq [IntPtr]::Zero) {
    Stop-Process -Id $mp.Id -Force -ErrorAction SilentlyContinue
    Write-Output "FAIL_NO_HOST"; exit 1
}

# 4. park the host at a fixed 4K spot at a modest size (config size may be huge),
#    let the maintain timer settle
[CT]::SetWindowPos($hw, [IntPtr]::Zero, 400, 150, 1100, 750, 0x0004) | Out-Null
Start-Sleep -Milliseconds 2500

# 5. expected pane rect in device px (XAML constants: border 2 DIP, topbar 28 DIP,
#    divider 6 DIP; ratio from config.json = the same value the host loaded at startup)
$hr = New-Object RECTT
[CT]::GetWindowRect($hw, [ref]$hr) | Out-Null
$scale = [CT]::GetDpiForWindow($hw) / 96.0
$cr = New-Object RECTT
[CT]::GetWindowRect($mph, [ref]$cr) | Out-Null
$cf = New-Object RECTT
[CT]::DwmGetWindowAttribute($mph, 9, [ref]$cf, 16) | Out-Null

$ratio = 0.5
$cfgPath = Join-Path $env:APPDATA "WindowMerger\config.json"
if (Test-Path $cfgPath) {
    try { $j = Get-Content $cfgPath -Raw | ConvertFrom-Json; if ($j.Ratio) { $ratio = [double]$j.Ratio } } catch {}
}
$wDip = ($hr.R - $hr.L) / $scale
$paneL = $hr.L + [int][Math]::Round(2 * $scale)
$paneT = $hr.T + [int][Math]::Round((2 + 28) * $scale)
$paneB = $hr.B - [int][Math]::Round(2 * $scale)
# child is attached --left: its visible right edge = left pane's right edge (divider edge)
$paneR = $hr.L + [int][Math]::Round((2 + ($wDip - 4 - 6) * $ratio) * $scale)

$okL = [Math]::Abs($cf.L - $paneL) -le 1
$okT = [Math]::Abs($cf.T - $paneT) -le 1
$okR = [Math]::Abs($cf.R - $paneR) -le 2
$okB = [Math]::Abs($cf.B - $paneB) -le 1
Write-Output ("HOST rect=({0},{1})-({2},{3}) dpi={4} scale={5} ratio={6}" -f $hr.L, $hr.T, $hr.R, $hr.B, [CT]::GetDpiForWindow($hw), $scale, $ratio)
Write-Output ("CHILD visible(extFB)=({0},{1})-({2},{3}) liveMargins(L={4},T={5},R={6},B={7})" -f `
    $cf.L, $cf.T, $cf.R, $cf.B, ($cf.L - $cr.L), ($cf.T - $cr.T), ($cr.R - $cf.R), ($cr.B - $cf.B))
Write-Output ("PANE expect L={0} T={1} R={2} B={3}" -f $paneL, $paneT, $paneR, $paneB)
Write-Output ("LEFT {0} (delta={1})  TOP {2} (delta={3})  RIGHT {4} (delta={5})  BOTTOM {6} (delta={7})" -f `
    ($(if ($okL) { "PASS" } else { "FAIL" })), ($cf.L - $paneL), `
    ($(if ($okT) { "PASS" } else { "FAIL" })), ($cf.T - $paneT), `
    ($(if ($okR) { "PASS" } else { "FAIL" })), ($cf.R - $paneR), `
    ($(if ($okB) { "PASS" } else { "FAIL" })), ($cf.B - $paneB))

# 6. cleanup: host graceful close (restores child), test mspaint killed
[CT]::PostMessageW($hw, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
Wait-Process -Id $host_.Id -Timeout 6 -ErrorAction SilentlyContinue
Stop-Process -Id $mp.Id -Force -ErrorAction SilentlyContinue
if ($okL -and $okT -and $okR -and $okB) { Write-Output "RESULT PASS"; exit 0 }
Write-Output "RESULT FAIL"; exit 1
