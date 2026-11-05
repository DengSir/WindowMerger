# ASCII-only: click into the left pane interior, report which process ends up foreground.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECT8 { public int L, T, R, B; }
public static class CK3 {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT8 r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
"@
[CK3]::SetProcessDPIAware() | Out-Null

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECT8
[CK3]::GetWindowRect($hm, [ref]$hr) | Out-Null
$avail = $hr.R - $hr.L - 4 - 8
$lx = [int]($hr.L + 2 + $avail * 0.3)
$my = [int](($hr.T + $hr.B) / 2)

[CK3]::SetCursorPos($lx, $my) | Out-Null
Start-Sleep -Milliseconds 200
[CK3]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[CK3]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 700

$fg = [CK3]::GetForegroundWindow()
$procId = 0
[CK3]::GetWindowThreadProcessId($fg, [ref]$procId) | Out-Null
$pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
Write-Output ("CLICK_LEFT_PANE -> FG=" + $pn)
