# ASCII-only: attach two classic cmd windows and verify click routing.
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct PT5 { public int X, Y; }
public struct RECT5 { public int L, T, R, B; }
public static class VI {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PT5 p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT5 r);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out int v, int s);
}
"@
[VI]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [VI]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECT5
[VI]::GetWindowRect($hm, [ref]$hr) | Out-Null
$avail = $hr.R - $hr.L - 4 - 8
$lx = [int]($hr.L + 2 + $avail * 0.3); $rx = [int]($hr.R - 2 - $avail * 0.3)
$my = [int](($hr.T + $hr.B) / 2)

foreach ($pt in @(@("LEFT", $lx), @("RIGHT", $rx))) {
    $p = New-Object PT5
    $p.X = [int]$pt[1]; $p.Y = $my
    $h = [VI]::WindowFromPoint($p)
    Write-Output ("{0}_CENTER -> proc={1} hwnd=0x{2:X}" -f $pt[0], (ProcOf $h), $h.ToInt64())
}


# divider click routing
$p2 = New-Object PT5
$p2.X = [int]($hr.L + 2 + $avail * 0.6018808777429467 + 4); $p2.Y = $my
$h2 = [VI]::WindowFromPoint($p2)
Write-Output ("DIVIDER -> proc=" + (ProcOf $h2))

# click into left pane, check foreground
[VI]::SetCursorPos($lx, $my) | Out-Null
Start-Sleep -Milliseconds 200
[VI]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[VI]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 700
$fg = [VI]::GetForegroundWindow()
Write-Output ("CLICK_LEFT -> FG proc=" + (ProcOf $fg))
