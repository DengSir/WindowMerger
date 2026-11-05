# ASCII-only: real Alt+Tab overlay capture with proper attach order.
# 1) kill all -> start notepad+mspaint -> clear iconic log -> start host (CLI attach)
# 2) verify children attached (TOOLWINDOW set)
# 3) hold ALT+TAB, screenshot the overlay, release
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AT2 {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTA3 p);
    public struct PTA3 { public int X, Y; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTA3 r);
    public struct RECTA3 { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
"@
[AT2]::SetProcessDPIAware() | Out-Null

Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "alttab-thumb"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 900
Start-Process mspaint
Start-Sleep -Milliseconds 1500
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
$hr = New-Object AT2+RECTA3
[AT2]::GetWindowRect($hm, [ref]$hr) | Out-Null
Write-Output ("HOST ({0},{1})-({2},{3})" -f $hr.L, $hr.T, $hr.R, $hr.B)

# attach verification: pane centers should hit the children
$avail = $hr.R - $hr.L - 4 - 8
$p1 = New-Object AT2+PTA3
$p1.X = [int]($hr.L + 2 + $avail * 0.35); $p1.Y = [int](($hr.T + $hr.B) / 2)
$p2 = New-Object AT2+PTA3
$p2.X = [int]($hr.L + 2 + $avail * 0.75); $p2.Y = [int](($hr.T + $hr.B) / 2)
foreach ($pp in @($p1, $p2)) {
    $h = [AT2]::WindowFromPoint($pp)
    $procId = 0
    [AT2]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    $pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
    Write-Output ("PANE_HIT=" + $pn)
}

# real ALT+TAB: hold ALT, tap TAB (opens overlay), wait, capture, release
[AT2]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 120
[AT2]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[AT2]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 2500

$bmp = New-Object System.Drawing.Bitmap(2560, 1440)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save("$env:TEMP\wm_alttab2.png")
$bmp.Dispose()
Write-Output "OVERLAY_SHOT_OK"

[AT2]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 800
Write-Output ALTAB_TEST_DONE
