# ASCII-only: minimize host -> verify children hidden; restore -> verify children visible.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class VM {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
}
"@
[VM]::SetProcessDPIAware() | Out-Null

$hostPid = (Get-Process WindowMerger -ErrorAction Stop).Id
$hm = (Get-Process WindowMerger).MainWindowHandle

$kids = Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 2
if (-not $kids) { Write-Output "NO_CHILDREN"; exit 1 }

function KidState {
    foreach ($k in $script:kids) {
        $h = [IntPtr]$k.MainWindowHandle
        Write-Output ("  {0} visible={1} iconic={2}" -f $k.ProcessName, [VM]::IsWindowVisible($h), [VM]::IsIconic($h))
    }
}

Write-Output "== BEFORE minimize =="
KidState

[VM]::ShowWindow($hm, 6) | Out-Null   # SW_MINIMIZE
Start-Sleep -Milliseconds 1200
Write-Output "== AFTER minimize (expect visible=False for both) =="
KidState

[VM]::ShowWindow($hm, 9) | Out-Null   # SW_RESTORE
Start-Sleep -Milliseconds 1200
Write-Output "== AFTER restore (expect visible=True for both) =="
KidState
