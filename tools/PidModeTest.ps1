# ASCII-only: PID-mode CLI attach end-to-end test.
# 1) start notepad (capture PID via -PassThru) + mspaint
# 2) launch host: --left <notepad PID> --right mspaint (mixed pid/name)
# 3) verify pane hits; then PID that has NO window -> notice path
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PTP { public int X, Y; }
public struct RECTP3 { public int L, T, R, B; }
public static class PIDT {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTP p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTP3 r);
}
"@
[PIDT]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [PIDT]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Set-Content "$env:TEMP\wmt1.txt" "pid-mode"

# start notepad ourselves -> PID in hand
$np = Start-Process notepad "$env:TEMP\wmt1.txt" -PassThru
Start-Sleep -Milliseconds 1200
Write-Output ("NOTEPAD_PID=" + $np.Id)
Start-Process mspaint
Start-Sleep -Milliseconds 1500

# mixed: left by PID, right by name
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", $np.Id, "--right", "mspaint"
Start-Sleep -Seconds 4

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECTP3
[PIDT]::GetWindowRect($hm, [ref]$hr) | Out-Null
$avail = $hr.R - $hr.L - 12
$p1 = New-Object PTP; $p1.X = [int]($hr.L + 2 + $avail * 0.35); $p1.Y = [int](($hr.T + $hr.B) / 2)
$p2 = New-Object PTP; $p2.X = [int]($hr.L + 2 + $avail * 0.75); $p2.Y = [int](($hr.T + $hr.B) / 2)
Write-Output ("LEFT_HIT=" + (ProcOf ([PIDT]::WindowFromPoint($p1))))
Write-Output ("RIGHT_HIT=" + (ProcOf ([PIDT]::WindowFromPoint($p2))))

# negative: PID of a windowless process (current powershell) -> notice path, host stays intact
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", $PID
Start-Sleep -Seconds 3
Write-Output ("NO_WINDOW_PID_TEST_DONE (second instance shows notice; check no crash)")
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output PID_MODE_TEST_DONE
