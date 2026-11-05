# ASCII-only: FIRST-display test — launch+attach, NO hover, immediately Alt-Tab.
# The tile must show the pre-populated composite (not black) on the very first display.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class FD {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
}
"@
[FD]::SetProcessDPIAware() | Out-Null

Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "first-display"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 900
Start-Process mspaint
Start-Sleep -Milliseconds 1500
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 3

# FIRST Alt-Tab display ever: hold ALT (overlay opens, first tile display), shoot, release
[FD]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150
[FD]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 50
[FD]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 1200
$bmp = New-Object System.Drawing.Bitmap(2560, 1440)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save("$env:TEMP\wm_first_display.png")
$bmp.Dispose()
Write-Output "FIRST_SHOT_OK"
[FD]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 600
Write-Output "--- request log ---"
Get-Content "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Write-Output FIRST_DISPLAY_TEST_DONE
