param(
    [Parameter(Mandatory = $true)][long]$Hwnd
)

# ASCII-only diagnostic: who covers the host, does TOPMOST stick, when is it cleared.
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class ZDiag {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern IntPtr GetTopWindow();
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder sb, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    public struct POINT { public int X, Y; }
}
"@
[ZDiag]::SetProcessDPIAware() | Out-Null

function InfoOf([IntPtr]$h) {
    $procId = 0
    [ZDiag]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    $pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
    $t = New-Object System.Text.StringBuilder 128
    [ZDiag]::GetWindowText($h, $t, 128) | Out-Null
    return ("0x{0:X} proc={1} title=[{2}]" -f $h.ToInt64(), $pn, $t.ToString())
}

Write-Output ("TARGET " + (InfoOf ([IntPtr]$Hwnd)))

# who is at the top bar point right now
$p = New-Object ZDiag+POINT
$p.X = 700; $p.Y = 310
$hit = [ZDiag]::WindowFromPoint($p)
Write-Output ("COVERING " + (InfoOf $hit))

# z chain top 6 visible windows
$cur = [ZDiag]::GetTopWindow()
for ($i = 0; $i -lt 6 -and $cur -ne [IntPtr]::Zero; $i++) {
    if ([ZDiag]::IsWindowVisible($cur)) { Write-Output ("Z$i " + (InfoOf $cur)) }
    $cur = [ZDiag]::GetWindow($cur, 3)   # GW_HWNDNEXT
}

# try topmost, watch the flag
$r = [ZDiag]::SetWindowPos([IntPtr]$Hwnd, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
$f0 = (([ZDiag]::GetWindowLong([IntPtr]$Hwnd, -20) -band 0x8) -ne 0)
Start-Sleep -Milliseconds 50
$f1 = (([ZDiag]::GetWindowLong([IntPtr]$Hwnd, -20) -band 0x8) -ne 0)
Start-Sleep -Milliseconds 500
$f2 = (([ZDiag]::GetWindowLong([IntPtr]$Hwnd, -20) -band 0x8) -ne 0)
Write-Output ("TOPMOST ret={0} t0={1} t50={2} t550={3}" -f $r, $f0, $f1, $f2)

# ALT trick then foreground
[ZDiag]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
[ZDiag]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
$null = [ZDiag]::SetWindowPos([IntPtr]$Hwnd, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
$fg = [ZDiag]::GetForegroundWindow()
Write-Output ("FG_IS_HOST={0}" -f ($fg -eq [IntPtr]$Hwnd))
$hit2 = [ZDiag]::WindowFromPoint($p)
Write-Output ("HIT_TOPBAR_AFTER " + (InfoOf $hit2))
