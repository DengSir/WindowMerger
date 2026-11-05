# ASCII-only: minimize host -> children off-screen; restore -> children back at panes.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECT6 { public int L, T, R, B; }
public static class VO {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT6 r);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
}
"@
[VO]::SetProcessDPIAware() | Out-Null

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }

function RectOf([IntPtr]$h) {
    $r = New-Object RECT6
    [VO]::GetWindowRect($h, [ref]$r) | Out-Null
    Write-Output ("  ({0},{1})-({2},{3})" -f $r.L, $r.T, $r.R, $r.B)
}

function KidRects {
    Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
        Write-Output ("  {0}:" -f $_.ProcessName)
        RectOf $_.MainWindowHandle
    }
}

[VO]::ShowWindow($hm, 6) | Out-Null   # SW_MINIMIZE
Start-Sleep -Milliseconds 1200
Write-Output "== MINIMIZED: children rects (expect -32000,-32000) =="
KidRects

[VO]::ShowWindow($hm, 9) | Out-Null   # SW_RESTORE
Start-Sleep -Milliseconds 1500
Write-Output "== RESTORED: children rects (expect back at panes) =="
KidRects
