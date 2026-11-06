# ASCII-only: read-only z-order dump. Do not move/kill any window.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PTD2 { public int X, Y; }
public struct RECTD2 { public int L, T, R, B; }
public static class ZD {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr GetTopWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTD2 r);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTD2 p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
"@
[ZD]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [ZD]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
$fg = [ZD]::GetForegroundWindow()
Write-Output ("FG proc={0}" -f (ProcOf $fg))

if ($hm -ne [IntPtr]::Zero) {
    $hr = New-Object RECTD2
    [ZD]::GetWindowRect($hm, [ref]$hr) | Out-Null
    Write-Output ("HOST rect=({0},{1})-({2},{3})" -f $hr.L, $hr.T, $hr.R, $hr.B)
    $avail = $hr.R - $hr.L - 12
    foreach ($pt in @(@("TOPBAR", [int](($hr.L+$hr.R)/2), ($hr.T+14)), @("LEFT", [int]($hr.L+2+$avail*0.35), [int](($hr.T+$hr.B)/2)), @("RIGHT", [int]($hr.L+2+$avail*0.75), [int](($hr.T+$hr.B)/2)))) {
        $p = New-Object PTD2; $p.X = [int]$pt[1]; $p.Y = [int]$pt[2]
        $h = [ZD]::WindowFromPoint($p)
        Write-Output ("HIT {0,-6} proc={1}" -f $pt[0], (ProcOf $h))
    }
}

Write-Output "--- z-order top 30 visible windows ---"
$cur = [ZD]::GetTopWindow([IntPtr]::Zero)
for ($i = 0; $i -lt 30 -and $cur -ne [IntPtr]::Zero; $i++) {
    if ([ZD]::IsWindowVisible($cur)) {
        $ex = [ZD]::GetWindowLong($cur, -20)
        $t = New-Object System.Text.StringBuilder 64
        [ZD]::GetWindowText($cur, $t, 64) | Out-Null
        $r = New-Object RECTD2
        [ZD]::GetWindowRect($cur, [ref]$r) | Out-Null
        $topmost = ($ex -band 0x8) -ne 0
        $tool = ($ex -band 0x80) -ne 0
        $mark = ""
        if ($cur -eq $hm) { $mark = " <== HOST" }
        Write-Output ("Z{0,-2} {1,-12} topmost={2} tool={3} y={4} [{5}]{6}" -f $i, (ProcOf $cur), $topmost, $tool, $r.T, $t.ToString(), $mark)
    }
    $cur = [ZD]::GetWindow($cur, 2)   # GW_HWNDNEXT
}
Write-Output DUMP_DONE
