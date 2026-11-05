# ASCII-only: hold ALT, press TAB to open the Alt+Tab overlay, wait, screenshot, release.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ATS {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
[ATS]::SetProcessDPIAware() | Out-Null

# ALT down, TAB down+up (opens overlay / cycles)
[ATS]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 120
[ATS]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[ATS]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 2000

# keep ALT held while capturing the overlay
$bmp = New-Object System.Drawing.Bitmap(2560, 1392)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$g.Dispose()
$small = New-Object System.Drawing.Bitmap(1280, 696)
$g2 = [System.Drawing.Graphics]::FromImage($small)
$g2.DrawImage($bmp, 0, 0, 1280, 696)
$g2.Dispose()
$small.Save('C:\Users\Dencer\AppData\Local\Temp\wm_alttab.png')
$bmp.Dispose()
$small.Dispose()

# release ALT, move cursor to center so the preview follows
[ATS]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
[ATS]::SetCursorPos(1280, 700) | Out-Null
Write-Output "ALT_SHOT_OK"
