# ASCII-only. Full regression flow for WindowMerger:
# cleanup -> open test windows -> CLI launch (--left/--right named args) ->
# verify attach/hit-tests/child rects -> restore topmost state.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PT { public int X, Y; }
public struct RECT2 { public int L, T, R, B; }
public static class TF {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PT p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT2 r);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
"@
[TF]::SetProcessDPIAware() | Out-Null

function ProcName([IntPtr]$h) {
    $procId = 0
    [TF]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

# 1. cleanup
Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:TEMP\wm-composite.log" -ErrorAction SilentlyContinue

# 2. test windows
Set-Content "$env:TEMP\wmt1.txt" "cli-test-1"
Set-Content "$env:TEMP\wmt2.txt" "cli-test-2"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 700
Start-Process mspaint
Start-Sleep -Milliseconds 1500

# 3. launch host with named args
$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Process $exe -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4

$hm = (Get-Process WindowMerger -ErrorAction SilentlyContinue).MainWindowHandle
if ($hm -eq 0 -or $null -eq $hm) { Write-Output "FAIL host-not-running"; exit 1 }
$hr = New-Object RECT2
[TF]::GetWindowRect($hm, [ref]$hr) | Out-Null
Write-Output ("HOST (" + $hr.L + "," + $hr.T + ")-(" + $hr.R + "," + $hr.B + ")")

# 4. hit tests at pane centers (0.25 / 0.75 of content width; the old 0.5 probes sat
#    on the pane split boundary and probed the wrong pane)
$p = New-Object PT
$p.X = [int]($hr.L + 2 + ($hr.R - $hr.L - 4 - 8) * 0.25); $p.Y = [int](($hr.T + $hr.B) / 2)
$h1 = [TF]::WindowFromPoint($p)
Write-Output ("LEFT_HIT proc=" + (ProcName $h1))
$p.X = [int]($hr.L + 2 + ($hr.R - $hr.L - 4 - 8) * 0.75)
$h2 = [TF]::WindowFromPoint($p)
Write-Output ("RIGHT_HIT proc=" + (ProcName $h2))

# 5. child rects vs panes (margins 7/0/7/7)
$ratio = 0.6018808777429467
try { $ratio = (Get-Content "$env:APPDATA\WindowMerger\config.json" -Raw | ConvertFrom-Json).Ratio } catch {}
$paneW = [int](($hr.R - $hr.L - 4 - 8) * $ratio)
$expL = ($hr.L + 2 - 7), ($hr.T + 2 + 28 - 0), ($hr.L + 2 + $paneW + 7), ($hr.B - 2 + 7)
Get-Process Notepad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    $r = New-Object RECT2
    [TF]::GetWindowRect($_.MainWindowHandle, [ref]$r) | Out-Null
    $dx = [Math]::Abs($r.L - $expL[0]) + [Math]::Abs($r.T - $expL[1]) + [Math]::Abs($r.R - $expL[2]) + [Math]::Abs($r.B - $expL[3])
    Write-Output ("LEFT_CHILD rect=({0},{1})-({2},{3}) paneDeviation={4}" -f $r.L, $r.T, $r.R, $r.B, $dx)
}
$expR0 = ($hr.L + 2 + $paneW + 8 - 7)
Get-Process mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    $r = New-Object RECT2
    [TF]::GetWindowRect($_.MainWindowHandle, [ref]$r) | Out-Null
    $dx = [Math]::Abs($r.L - $expR0) + [Math]::Abs($r.T - ($hr.T + 30)) + [Math]::Abs($r.R - ($hr.R - 2 + 7)) + [Math]::Abs($r.B - ($hr.B - 2 + 7))
    Write-Output ("RIGHT_CHILD rect=({0},{1})-({2},{3}) paneDeviation={4}" -f $r.L, $r.T, $r.R, $r.B, $dx)
}

# 6. no topmost residue
[TF]::SetWindowPos($hm, [IntPtr](-2), 0, 0, 0, 0, 0x0003) | Out-Null
Write-Output FLOW_DONE
