# ASCII-only: verify minimized live-preview uses restored size (not 160x99 ghost).
# 1) fresh attach, minimize host (children go offscreen)
# 2) synthetic WM_DWMSENDICONICLIVEPREVIEWBITMAP + WM_DWMSENDICONICTHUMBNAIL
# 3) log must show LIVEPREVIEW <restored size> iconic=True (not ~160x99)
# 4) real Alt+Tab overlay capture for visual, then restore + close
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class MP {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTM3 r);
    public struct RECTM3 { public int L, T, R, B; }
}
"@
[MP]::SetProcessDPIAware() | Out-Null

Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "minimized-preview"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 900
Start-Process mspaint
Start-Sleep -Milliseconds 1500
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle

# capture normal rect before minimizing (placement size reference)
$nr = New-Object MP+RECTM3
[MP]::GetWindowRect($hm, [ref]$nr) | Out-Null
Write-Output ("NORMAL_RECT {0}x{1}" -f ($nr.R - $nr.L), ($nr.B - $nr.T))

# minimize -> children offscreen
$null = [MP]::ShowWindow($hm, 6)   # SW_MINIMIZE
Start-Sleep -Milliseconds 1000
Write-Output ("MINIMIZED=" + [MP]::IsIconic($hm))

# ghost rect while minimized (what the old bug used)
$gr = New-Object MP+RECTM3
[MP]::GetWindowRect($hm, [ref]$gr) | Out-Null
Write-Output ("GHOST_RECT {0}x{1} at ({2},{3})" -f ($gr.R - $gr.L), ($gr.B - $gr.T), $gr.L, $gr.T)

# synthetic iconic requests
$null = [MP]::SendMessage($hm, 0x0326, [IntPtr]::Zero, [IntPtr]::Zero)   # LIVEPREVIEW
Start-Sleep -Milliseconds 400
$wReq = [IntPtr]((500 -shl 16) -bor 300)
$null = [MP]::SendMessage($hm, 0x0323, $wReq, [IntPtr]::Zero)            # THUMBNAIL 500x300
Start-Sleep -Milliseconds 400

Write-Output "--- iconic log ---"
Get-Content "$env:TEMP\wm-iconic.log" -ErrorAction SilentlyContinue

# real Alt+Tab overlay capture while minimized
[MP]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 120
[MP]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[MP]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 2500
$bmp = New-Object System.Drawing.Bitmap(2560, 1440)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save("$env:TEMP\wm_alttab_min.png")
$bmp.Dispose()
Write-Output "OVERLAY_SHOT_OK"
[MP]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 600

# restore host (children come back), then graceful close
$null = [MP]::ShowWindow($hm, 9)   # SW_RESTORE
Start-Sleep -Milliseconds 800
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm) { $null = $p.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-OUTPUT MIN_PREVIEW_TEST_DONE
