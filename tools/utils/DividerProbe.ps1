# ASCII-only: probe that the divider strip is hit by the HOST window now
# (children glued below host => host chrome covers the divider).
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PTDIV { public int X, Y; }
public struct RECTDIV { public int L, T, R, B; }
public static class DP {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTDIV p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTDIV r);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
"@
[DP]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [DP]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECTDIV
[DP]::GetWindowRect($hm, [ref]$hr) | Out-Null
$ratio = 0.5
try { $ratio = (Get-Content "$env:APPDATA\WindowMerger\config.json" -Raw | ConvertFrom-Json).Ratio } catch {}
$avail = $hr.R - $hr.L - 4 - 8
$divX = [int]($hr.L + 2 + $avail * $ratio + 4)   # divider center (8px wide)
$midY = [int](($hr.T + $hr.B) / 2)
foreach ($dx in 0..7) {
    $p = New-Object PTDIV
    $p.X = [int]($hr.L + 2 + $avail * $ratio) + $dx; $p.Y = $midY
    $h = [DP]::WindowFromPoint($p)
    Write-Output ("DIVIDER+{0}: {1}" -f $dx, (ProcOf $h))
}
$p = New-Object PTDIV
$p.X = $divX; $p.Y = $midY
Write-Output ("DIVIDER_CENTER2 x={0}: {1}" -f $divX, (ProcOf ([DP]::WindowFromPoint($p))))
Write-Output DIVIDER_PROBE_DONE
