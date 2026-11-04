param(
    [Parameter(Mandatory = $true)][long]$Hwnd,
    [Parameter(Mandatory = $true)][int]$ProcId,
    [switch]$NoTopmost
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinFocus {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    public struct POINT { public int X, Y; }
}
"@

$h = [IntPtr]$Hwnd
$ws = New-Object -ComObject WScript.Shell
$null = $ws.AppActivate($ProcId)
Start-Sleep -Milliseconds 200

$insert = if ($NoTopmost) { [IntPtr](-2) } else { [IntPtr](-1) }  # -1 topmost, -2 notopmost
[WinFocus]::SetWindowPos($h, $insert, 0, 0, 0, 0, 0x0003) | Out-Null  # NOSIZE|NOMOVE
Start-Sleep -Milliseconds 300

$topmost = (([WinFocus]::GetWindowLong($h, -20) -band 0x8) -ne 0)
$fg = [WinFocus]::GetForegroundWindow() -eq $h
Write-Output ("TOPMOST={0} FOREGROUND={1}" -f $topmost, $fg)

$p = New-Object WinFocus+POINT
$p.X = 700; $p.Y = 310   # 顶条中心区域
$hit = [WinFocus]::WindowFromPoint($p)
Write-Output ("HIT_TOPBAR=0x{0:X} IS_HOST={1}" -f $hit.ToInt64(), ($hit -eq $h))
