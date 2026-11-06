param(
    [Parameter(Mandatory = $true)][int]$X1,
    [Parameter(Mandatory = $true)][int]$Y1,
    [Parameter(Mandatory = $true)][int]$X2,
    [Parameter(Mandatory = $true)][int]$Y2,
    [int]$Steps = 30,
    [int]$DelayMs = 20
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class MouseDrag {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtra);
    public const uint LEFTDOWN = 0x0002;
    public const uint LEFTUP = 0x0004;
}
"@
[MouseDrag]::SetProcessDPIAware() | Out-Null

[MouseDrag]::SetCursorPos($X1, $Y1) | Out-Null
Start-Sleep -Milliseconds 120
[MouseDrag]::mouse_event([MouseDrag]::LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 120

for ($i = 1; $i -le $Steps; $i++) {
    $x = $X1 + [int](($X2 - $X1) * $i / $Steps)
    $y = $Y1 + [int](($Y2 - $Y1) * $i / $Steps)
    [MouseDrag]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds $DelayMs
}

Start-Sleep -Milliseconds 120
[MouseDrag]::mouse_event([MouseDrag]::LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150
Write-Output "DRAG_DONE ($X1,$Y1)->($X2,$Y2)"
