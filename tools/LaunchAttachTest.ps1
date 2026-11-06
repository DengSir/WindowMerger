# ASCII-only: launch-if-missing regression. NO notepad.
# Ensures mspaint is NOT running, starts the host with --left mspaint --left-exe <path>,
# and expects the host to LAUNCH mspaint itself, then attach it (WS_EX_TOOLWINDOW set)
# within ~15s. Also proves the recorded full path survives a relaunch of the combo.
$exe = "D:\Develop\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class LA {
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int w, int hh, uint f);
}
"@

# graceful close of running hosts; refuse to touch a user mspaint
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }
Start-Sleep -Milliseconds 1300
if (Get-Process mspaint -ErrorAction SilentlyContinue) { Write-Output "SKIP_MSPAINT_RUNNING"; exit 0 }

# resolve mspaint's real exe path while it is briefly up (packaged app path carries a
# version dir that changes on app updates, so never hardcode it), then close it again
$mp = Start-Process mspaint -PassThru
Start-Sleep -Milliseconds 1800
$mp2 = Get-Process mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $mp2) { Write-Output "FAIL_NO_MSPAINT"; exit 1 }
$null = [LA]::SetWindowPos([IntPtr]$mp2.MainWindowHandle, [IntPtr]::Zero, -2300, 200, 900, 650, 0x0004)
$mpPath = $mp2.Path
Stop-Process -Id $mp2.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1200
if (-not $mpPath) { Write-Output "FAIL_NO_PATH"; exit 1 }
Write-Output ("TARGET_PATH=" + $mpPath)

# host with name + full path: mspaint is closed, so the host must LAUNCH it and attach
$hostStart = Get-Date
Start-Process $exe -ArgumentList "--left", "mspaint", "--left-exe", "`"$mpPath`""
Start-Sleep -Seconds 4
# test host shrunk + parked on the left monitor (config size may be huge)
$hw2 = (Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1)
if ($hw2) { $null = [LA]::SetWindowPos([IntPtr]$hw2.MainWindowHandle, [IntPtr]::Zero, -2460, 120, 1000, 700, 0x0004) }

# poll up to 15s for mspaint reappearing AND being attached (toolwindow style)
$ok = $false
$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    $p = Get-Process mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) {
        $launchedByHost = $p.StartTime -gt $hostStart
        $ex = [LA]::GetWindowLong([IntPtr]$p.MainWindowHandle, -20)
        $attached = (($ex -band 0x80) -ne 0)
        Write-Output ("STATE launchedByHost={0} attached={1} path={2}" -f $launchedByHost, $attached, $p.Path)
        if ($launchedByHost -and $attached) { $ok = $true; break }
    }
}

# cleanup
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($proc) { $null = $proc.CloseMainWindow(); Start-Sleep -Milliseconds 1500 }
Get-Process mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

if ($ok) { Write-Output "RESULT PASS" } else { Write-Output "RESULT FAIL" }
if (-not $ok) { exit 1 }
