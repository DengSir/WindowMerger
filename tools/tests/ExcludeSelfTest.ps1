# ASCII-only: verify grabbing excludes "another self" - a second WindowMerger
# instance's host window must NOT be dockable via CLI (--left <its pid>): no
# TOOLWINDOW set on it, rect untouched. Victim launches first, then the CLI
# grabber (attach happens at Loaded, target must exist).
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECI { public int L, T, R, B; }
public static class XI {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECI r);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
}
"@
[XI]::SetProcessDPIAware() | Out-Null

$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"

# cleanup (graceful; instances may hold user windows, so no force kill here)
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }
Start-Sleep -Milliseconds 1300

# victim: plain instance B
Start-Process $exe
Start-Sleep -Seconds 3
$b = Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $b) { Write-Output "FAIL_NO_B"; exit 1 }
$hb = [IntPtr]$b.MainWindowHandle
$rb = New-Object RECI
[XI]::GetWindowRect($hb, [ref]$rb) | Out-Null

# grabber: instance C targeting B's host by PID
Start-Process $exe -ArgumentList "--left", "$($b.Id)"
Start-Sleep -Seconds 4

$c = Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $b.Id -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $c) { Write-Output "FAIL_NO_C"; exit 1 }

$tool = (([XI]::GetWindowLong($hb, -20)) -band 0x80) -ne 0
$rb2 = New-Object RECI
[XI]::GetWindowRect($hb, [ref]$rb2) | Out-Null
$moved = ($rb2.L -ne $rb.L) -or ($rb2.T -ne $rb.T)

if (-not $tool -and -not $moved) {
    Write-Output ("PASS other-self not grabbed: B pid={0} toolwindow={1} moved={2}" -f $b.Id, $tool, $moved)
} else {
    Write-Output ("FAIL B was grabbed: toolwindow={0} moved={1}" -f $tool, $moved)
}

# cleanup (graceful so both instances release/exit cleanly)
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Write-Output EXCLUDE_SELF_TEST_DONE
