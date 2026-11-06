# ASCII-only: full state probe — host, children, hit tests, foreground.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PTD { public int X, Y; }
public struct RECTD { public int L, T, R, B; }
public static class SP {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTD p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTD r);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out int v, int s);
}
"@
[SP]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [SP]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object SP+RECTD
[SP]::GetWindowRect($hm, [ref]$hr) | Out-Null
Write-Output ("HOST 0x{0:X} rect=({1},{2})-({3},{4})" -f $hm.ToInt64(), $hr.L, $hr.T, $hr.R, $hr.B)

$avail = $hr.R - $hr.L - 4 - 8
foreach ($f in @(@("LEFT", 0.3), @("RIGHT", 0.75))) {
    $p = New-Object SP+PTD
    $p.X = [int]($hr.L + 2 + $avail * [double]$f[1]); $p.Y = [int](($hr.T + $hr.B) / 2)
    $h = [SP]::WindowFromPoint($p)
    Write-Output ("{0}_CENTER proc={1}" -f $f[0], (ProcOf $h))
}
$fg = [SP]::GetForegroundWindow()
Write-Output ("FG proc=" + (ProcOf $fg))
