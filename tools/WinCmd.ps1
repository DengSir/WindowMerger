param(
    [long]$Hwnd = 0,
    [Parameter(Mandatory = $true)][ValidateSet("minimize", "restore", "close")][string]$Action
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinCmd {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, UIntPtr w, IntPtr l);
    public const int SW_MINIMIZE = 6;
    public const int SW_RESTORE = 9;
    public const uint WM_CLOSE = 0x0010;
}
"@

$h = [IntPtr]$Hwnd
if ($h -eq [IntPtr]::Zero) { Write-Output "NOT_FOUND"; exit 1 }

switch ($Action) {
    "minimize" { [WinCmd]::ShowWindow($h, [WinCmd]::SW_MINIMIZE) | Out-Null }
    "restore"  { [WinCmd]::ShowWindow($h, [WinCmd]::SW_RESTORE) | Out-Null }
    "close"    { [WinCmd]::PostMessage($h, [WinCmd]::WM_CLOSE, [UIntPtr]::Zero, [IntPtr]::Zero) | Out-Null }
}
Start-Sleep -Milliseconds 400
Write-Output "CMD_OK $Action hwnd=$h"
