param(
    [Parameter(Mandatory = $true)][int]$X,
    [Parameter(Mandatory = $true)][int]$Y
)

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class WinHit {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    public struct POINT { public int X, Y; }
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder sb, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[WinHit]::SetProcessDPIAware() | Out-Null

$p = New-Object WinHit+POINT
$p.X = $X; $p.Y = $Y
$h = [WinHit]::WindowFromPoint($p)
if ($h -eq [IntPtr]::Zero) { Write-Output "WINDOW=0"; exit }

$r = New-Object WinHit+RECT
[WinHit]::GetWindowRect($h, [ref]$r) | Out-Null
$t = New-Object System.Text.StringBuilder 256
[WinHit]::GetWindowText($h, $t, 256) | Out-Null
$c = New-Object System.Text.StringBuilder 256
[WinHit]::GetClassName($h, $c, 256) | Out-Null
$procId = 0
[WinHit]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
$procName = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }

Write-Output ("HWND=0x{0:X} RECT=({1},{2},{3},{4}) CLASS={5} PID={6} PROC={7} TITLE={8}" -f `
    $h.ToInt64(), $r.Left, $r.Top, $r.Right, $r.Bottom, $c.ToString(), $procId, $procName, $t.ToString())
