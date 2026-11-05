# ASCII-only. wParam is unused; lParam carries max size: HIWORD=width 400, LOWORD=height 250.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class TT {
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[TT]::SetProcessDPIAware() | Out-Null

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }

$lParam = [IntPtr](((400 -shl 16) -bor 250))
[TT]::SendMessage($hm, 0x0323, [IntPtr]::Zero, $lParam) | Out-Null
Start-Sleep -Milliseconds 300
$alive = (Get-Process WindowMerger -ErrorAction SilentlyContinue) -ne $null
Write-Output ("THUMB_TRIGGERED hwnd=0x{0:X} alive={1}" -f $hm.ToInt64(), $alive)
