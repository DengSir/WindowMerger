param(
    [long]$HostHwnd = 0
)

# ASCII-only: verify attach state, force-iconic attr, and what sits in each pane.
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct PT { public int X, Y; }
public struct RECT2 { public int L, T, R, B; }
public static class CP {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PT p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out int v, int s);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT2 r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
}
"@
[CP]::SetProcessDPIAware() | Out-Null

$hm = [IntPtr]$HostHwnd
$v = 0
[CP]::DwmGetWindowAttribute($hm, 7, [ref]$v, 4) | Out-Null
Write-Output ("FORCE_ICONIC=" + $v)

$procId = 0
$p = New-Object PT
$p.X = 700; $p.Y = 700
$h = [CP]::WindowFromPoint($p)
[CP]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
$pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
Write-Output ("LEFT_CENTER proc=" + $pn)

$p.X = 1900; $p.Y = 700
$h = [CP]::WindowFromPoint($p)
[CP]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
$pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
Write-Output ("RIGHT_CENTER proc=" + $pn)

Get-Process Notepad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    $r = New-Object RECT2
    [CP]::GetWindowRect($_.MainWindowHandle, [ref]$r) | Out-Null
    $t = New-Object System.Text.StringBuilder 128
    [CP]::GetWindowText($_.MainWindowHandle, $t, 128) | Out-Null
    Write-Output ("NOTEPAD 0x{0:X} iconic={1} rect=({2},{3})-({4},{5}) title=[{6}]" -f `
        $_.MainWindowHandle.ToInt64(), [CP]::IsIconic($_.MainWindowHandle), $r.L, $r.T, $r.R, $r.B, $t.ToString())
}
