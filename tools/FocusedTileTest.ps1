# ASCII-only: capture our tile in FOCUSED state during Alt-Tab.
# Hold ALT, tap TAB repeatedly; after each tap save a full screenshot.
# Our tile is at a FIXED grid position; the focused tap = the frame where our
# tile has the enlarged highlight. Log every THUMBNAIL request with timestamps.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class FT {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
}
"@
[FT]::SetProcessDPIAware() | Out-Null

Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "focused-tile"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 900
Start-Process mspaint
Start-Sleep -Milliseconds 1500
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }

# put another window foreground first (host becomes 2nd in MRU)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class FT2 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr FindWindowW(string cls, string title);
}
"@
$edge = [FT2]::FindWindowW($null, "Untitled - Figma")
if ($edge -ne [IntPtr]::Zero) { $null = [FT2]::SetForegroundWindow($edge) }
Start-Sleep -Milliseconds 600

[FT]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)   # ALT down
Start-Sleep -Milliseconds 150
[FT]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)   # TAB down
Start-Sleep -Milliseconds 60
[FT]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)   # TAB up
Start-Sleep -Milliseconds 700

for ($i = 1; $i -le 8; $i++) {
    $bmp = New-Object System.Drawing.Bitmap(2560, 1440)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
    $g.Dispose()
    $bmp.Save("$env:TEMP\wm_ft_$i.png")
    $bmp.Dispose()
    [FT]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 50
    [FT]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 550
}
[FT]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)   # ALT up (switch happens)
Start-Sleep -Milliseconds 600
Write-Output "FRAMES_SAVED"
Get-Content "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Write-Output FOCUSED_TEST_DONE
