# ASCII-only: drag Notepad into host left pane, verify snap rect. All coords read live.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AT {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[AT]::SetProcessDPIAware() | Out-Null

$hostH = (Get-Process WindowMerger -ErrorAction Stop).MainWindowHandle
$npP = Get-Process Notepad -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$npH = $npP.MainWindowHandle

$hr = New-Object AT+RECT; [AT]::GetWindowRect($hostH, [ref]$hr) | Out-Null
$nr = New-Object AT+RECT; [AT]::GetWindowRect($npH, [ref]$nr) | Out-Null
Write-Output ("HOST RECT=({0},{1},{2},{3})" -f $hr.Left, $hr.Top, $hr.Right, $hr.Bottom)
Write-Output ("NOTEPAD RECT=({0},{1},{2},{3})" -f $nr.Left, $nr.Top, $nr.Right, $nr.Bottom)

$ratio = 0.5
$availW = ($hr.Right - $hr.Left) - 4 - 8
$paneW = [int]($availW * $ratio)
$paneH = ($hr.Bottom - $hr.Top) - 32
$px0 = $hr.Left + 2
$py0 = $hr.Top + 30
$paneCenterX = $px0 + [int]($paneW / 2)
$paneCenterY = $py0 + [int]($paneH / 2)

# raise notepad above everything so the grab cannot hit another window
$null = [AT]::SetWindowPos($npH, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
$null = [AT]::SetForegroundWindow($npH)
Start-Sleep -Milliseconds 400

# grab on the empty tab strip (avoid tabs and window buttons); drop so the WINDOW CENTER lands on pane center
$grabX = $nr.Right - 280
$grabY = $nr.Top + 15
$npW = $nr.Right - $nr.Left
$npHh = $nr.Bottom - $nr.Top
$endX = $paneCenterX
$endY = $paneCenterY - [int]($npHh / 2) + 15

Write-Output ("DRAG ({0},{1})->({2},{3}) expect pane rect=({4},{5},{6},{7})" -f `
    $grabX, $grabY, $endX, $endY, $px0, $py0, ($px0 + $paneW), ($py0 + $paneH))

[AT]::SetCursorPos($grabX, $grabY) | Out-Null
Start-Sleep -Milliseconds 150
[AT]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150
$steps = 40
for ($i = 1; $i -le $steps; $i++) {
    $x = $grabX + [int](($endX - $grabX) * $i / $steps)
    $y = $grabY + [int](($endY - $grabY) * $i / $steps)
    [AT]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds 20
}
Start-Sleep -Milliseconds 150
[AT]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 1000

$nr2 = New-Object AT+RECT
[AT]::GetWindowRect($npH, [ref]$nr2) | Out-Null
$dx = [Math]::Abs($nr2.Left - $px0) + [Math]::Abs($nr2.Top - $py0) + [Math]::Abs($nr2.Right - ($px0 + $paneW)) + [Math]::Abs($nr2.Bottom - ($py0 + $paneH))
Write-Output ("AFTER RECT=({0},{1},{2},{3}) DELTA_SUM={4}" -f $nr2.Left, $nr2.Top, $nr2.Right, $nr2.Bottom, $dx)
if ($dx -le 8) { Write-Output "ATTACH_PASS" } else { Write-Output "ATTACH_FAIL" }
