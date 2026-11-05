# ASCII-only: click-based focus repro — host title -> ZCode -> host title -> left pane, probing each step.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PTC { public int X, Y; }
public struct RECTC { public int L, T, R, B; }
public static class CRC {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTC p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTC r);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
"@
[CRC]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [CRC]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}
function ClickAt([int]$x, [int]$y) {
    [CRC]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds 150
    [CRC]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [CRC]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 600
}
function HitAt([int]$x, [int]$y) {
    $p = New-Object PTC
    $p.X = $x; $p.Y = $y
    $h = [CRC]::WindowFromPoint($p)
    ProcOf $h
}

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECTC
[CRC]::GetWindowRect($hm, [ref]$hr) | Out-Null
$avail = $hr.R - $hr.L - 4 - 8
$titleX = [int]($hr.L + ($hr.R - $hr.L) * 0.3); $titleY = $hr.T + 14
$lx = [int]($hr.L + 2 + $avail * 0.3); $my = [int](($hr.T + $hr.B) / 2)
$zx = $hr.R - 60; $zy = $hr.T + 40   # a point that may fall on ZCode/other windows

Write-Output ("HOST rect=({0},{1})-({2},{3})" -f $hr.L, $hr.T, $hr.R, $hr.B)

# step 1: click host title (activate host)
ClickAt $titleX $titleY
Write-Output ("S1_titleclick FG=" + (ProcOf ([CRC]::GetForegroundWindow())) + " left_hit=" + (HitAt $lx $my))

# step 2: click ZCode area (switch away)
ClickAt $zx $zy
Write-Output ("S2_zcodeclick FG=" + (ProcOf ([CRC]::GetForegroundWindow())) + " left_hit=" + (HitAt $lx $my))

# step 3: click host title (back to host)
ClickAt $titleX $titleY
Write-Output ("S3_titleclick FG=" + (ProcOf ([CRC]::GetForegroundWindow())) + " left_hit=" + (HitAt $lx $my))

# step 4: click into left pane (should activate notepad child)
ClickAt $lx $my
Write-Output ("S4_paneclick FG=" + (ProcOf ([CRC]::GetForegroundWindow())) + " left_hit=" + (HitAt $lx $my))
