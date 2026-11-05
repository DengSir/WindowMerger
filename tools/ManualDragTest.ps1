# ASCII-only: interactive maximize-drag verification.
# Prepares the environment (fresh host + notepad/mspaint attached), then YOU
# operate manually: maximize -> click top bar without moving -> drag the top bar.
# While you operate, the script samples window state every 150 ms into a timeline.
# Press ENTER in this console when done; the timeline is printed.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTI { public int L, T, R, B; }
public static class IV {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTI r);
    [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINTI p);
    public struct POINTI { public int X, Y; }
}
"@
[IV]::SetProcessDPIAware() | Out-Null

# 1. environment: cleanup, fresh config, test windows, host with children
Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:APPDATA\WindowMerger\config.json" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "manual-drag-1"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 700
Start-Process mspaint
Start-Sleep -Milliseconds 1500
$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Process $exe -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
Write-Output ("HOST 0x{0:X} ready." -f $hm.ToInt64())
Write-Output "OPERATE NOW: maximize -> click top bar (no move) -> drag top bar. Press ENTER when done."

# 2. sample every 150ms until user presses ENTER (runspace-free: raw ReadKey poll)
$log = New-Object System.Collections.Generic.List[string]
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$keyPressed = $false
while (-not $keyPressed) {
    $r = New-Object RECTI
    [IV]::GetWindowRect($hm, [ref]$r) | Out-Null
    $z = [IV]::IsZoomed($hm)
    $c = New-Object IV+POINTI
    [IV]::GetCursorPos([ref]$c) | Out-Null
    $log.Add(("{0,6} ms  zoomed={1,-5} rect=({2},{3})-({4},{5})  cursor=({6},{7})" -f $sw.ElapsedMilliseconds, $z, $r.L, $r.T, $r.R, $r.B, $c.X, $c.Y))
    if ([Console]::KeyAvailable) {
        $k = [Console]::ReadKey($true)
        if ($k.Key -eq [ConsoleKey]::Enter) { $keyPressed = $true }
    }
    Start-Sleep -Milliseconds 150
}

# 3. summarize: transitions of zoomed / position jumps
Write-Output ""
Write-Output "--- transitions (state changes only) ---"
$prev = ""
foreach ($line in $log) {
    $cur = ($line -replace "^\s*\d+ ms\s+", "")
    if ($cur -ne $prev) { Write-Output $line; $prev = $cur }
}
Write-Output ("SAMPLES=" + $log.Count)

# 4. keep windows for user inspection; host must be closed manually or by next test run
Write-Output MANUAL_TEST_DONE
