# ASCII-only: capture OUR tile in the FOCUSED (enlarged) Alt-Tab state.
# Flow: attach -> hover taskbar (populate 200x109 cache) -> ALT down, TAB
# (selection = tile 2), SHIFT+TAB (selection back to tile 1 = OURS, enlarged)
# -> screenshot while held -> dump request log.
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AF {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
[AF]::SetProcessDPIAware() | Out-Null

Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "focus-tile"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 900
Start-Process mspaint
Start-Sleep -Milliseconds 1500
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4
$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle

# 1. populate the thumbnail cache via taskbar hover
$root = [System.Windows.Automation.AutomationElement]::RootElement
$taskbar = $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "Shell_TrayWnd")))
$btn = $null
if ($taskbar -ne $null) {
    $all = $taskbar.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($e in $all) { if ($e.Current.Name -match "WindowMerger") { $btn = $e; break } }
}
if ($btn -eq $null) { Write-Output "NO_TASKBAR_BUTTON"; exit 1 }
$rc = $btn.Current.BoundingRectangle
$null = [AF]::SetCursorPos([int]($rc.X + $rc.Width / 2), [int]($rc.Y + $rc.Height / 2))
Start-Sleep -Milliseconds 1500
[AF]::SetCursorPos(10, 700) | Out-Null
Start-Sleep -Milliseconds 500

# 2. ALT down, TAB (sel=tile2), SHIFT+TAB (sel=tile1=OURS enlarged), hold and shoot
[AF]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)    # ALT down
Start-Sleep -Milliseconds 150
[AF]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)    # TAB down
Start-Sleep -Milliseconds 50
[AF]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)    # TAB up
Start-Sleep -Milliseconds 600
[AF]::keybd_event(0x10, 0, 0, [UIntPtr]::Zero)    # SHIFT down
Start-Sleep -Milliseconds 80
[AF]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)    # TAB down
Start-Sleep -Milliseconds 50
[AF]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)    # TAB up
Start-Sleep -Milliseconds 120
[AF]::keybd_event(0x10, 0, 2, [UIntPtr]::Zero)    # SHIFT up
Start-Sleep -Milliseconds 900

$bmp = New-Object System.Drawing.Bitmap(2560, 1440)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save("$env:TEMP\wm_ft_focus.png")
$bmp.Dispose()
Write-Output "FOCUS_SHOT_OK"

[AF]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)    # ALT up (cancel via... switches to ours = fine)
Start-Sleep -Milliseconds 600
Write-Output "--- request log ---"
Get-Content "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Write-Output FOCUS_TEST_DONE
