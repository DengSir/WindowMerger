# ASCII-only: end-to-end orphan cleanup verification.
# 1) attach notepad via CLI, force-kill host -> orphan toolwindow remains
# 2) scan: notepad window has TOOLWINDOW (orphan confirmed)
# 3) relaunch host: startup cleanup (hwnd-precise) must strip it
# 4) scan again: no TOOLWINDOW on notepad, window visible
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class OC {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@

function Scan-NotepadToolwindow {
    Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct RECTN { public int L, T, R, B; }
public static class NC {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr GetTopWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTN r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
}
"@
    [NC]::SetProcessDPIAware() | Out-Null
    $pids = @{}
    Get-Process Notepad -ErrorAction SilentlyContinue | ForEach-Object { $pids[$_.Id] = $true }
    $results = @()
    $cur = [NC]::GetTopWindow([IntPtr]::Zero)
    for ($i = 0; $i -lt 600 -and $cur -ne [IntPtr]::Zero; $i++) {
        $procId = 0
        [NC]::GetWindowThreadProcessId($cur, [ref]$procId) | Out-Null
        if ($pids.ContainsKey([int]$procId)) {
            $ex = [NC]::GetWindowLong($cur, -20)
            $tool = ($ex -band 0x80) -ne 0
            $tb = New-Object System.Text.StringBuilder 64
            [NC]::GetWindowText($cur, $tb, 64) | Out-Null
            if ($tool -or $tb.Length -gt 0) {
                $r = New-Object RECTN
                [NC]::GetWindowRect($cur, [ref]$r) | Out-Null
                $results += ("hwnd=0x{0:X} tool={1} vis={2} rect=({3},{4}) title=[{5}]" -f $cur.ToInt64(), $tool, [NC]::IsWindowVisible($cur), $r.L, $r.T, $tb.ToString())
            }
        }
        $cur = [NC]::GetWindow($cur, 2)
    }
    return $results
}

# 1. fresh state: kill all, remove config, start notepad
Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:APPDATA\WindowMerger\config.json" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "orphan-e2e"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 1500

# 2. attach via CLI then FORCE-KILL the host -> orphan
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad"
Start-Sleep -Seconds 4
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $wm) { Write-Output "NO_HOST"; exit 1 }
Write-Output "CONFIG_PIDS_SAVED:"
Get-Content "$env:APPDATA\WindowMerger\config.json" | Select-String -Pattern "Attached"
Stop-Process -Id $wm.Id -Force   # the incident: force-kill with child attached
Start-Sleep -Milliseconds 800

Write-Output "--- scan after force-kill (expect tool=True orphan) ---"
Scan-NotepadToolwindow | ForEach-Object { Write-Output $_ }

# 3. relaunch host (no CLI): startup cleanup must rescue the orphan
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Sleep -Seconds 4

Write-Output "--- scan after relaunch (expect tool=False, vis=True) ---"
Scan-NotepadToolwindow | ForEach-Object { Write-Output $_ }

# 4. cleanup test env
$wm2 = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm2) { $null = $p.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output ORPHAN_E2E_DONE
