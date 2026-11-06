# ASCII-only: visual check of the theme dropdown — launch, topmost, real click
# on the theme button, screenshot the open menu, ESC + NOTOPMOST + close.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTS { public int L, T, R, B; }
public static class TMS {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTS r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
}
"@
[TMS]::SetProcessDPIAware() | Out-Null

$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Process $exe
Start-Sleep -Seconds 3

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECTS
[TMS]::GetWindowRect($hm, [ref]$hr) | Out-Null
Write-Output ("HOST ({0},{1})-({2},{3})" -f $hr.L, $hr.T, $hr.R, $hr.B)

# topmost so the real click lands on the host (Atomic pattern; restored later)
$null = [TMS]::SetWindowPos($hm, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
Start-Sleep -Milliseconds 300

$bx = $hr.R - 4 - 139
$by = $hr.T + 16
[TMS]::SetCursorPos($bx, $by) | Out-Null
Start-Sleep -Milliseconds 150
[TMS]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 60
[TMS]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 800

# full-screen capture then crop around button + dropdown
$big = New-Object System.Drawing.Bitmap(2560, 1440)
$g = [System.Drawing.Graphics]::FromImage($big)
$g.CopyFromScreen(0, 0, 0, 0, $big.Size)
$g.Dispose()
$capW = 420; $capH = 260
$capX = [Math]::Max(0, $bx - 340); $capY = [Math]::Max(0, $hr.T)
$small = $big.Clone([System.Drawing.Rectangle]::new($capX, $capY, $capW, $capH), $big.PixelFormat)
$small.Save("$env:TEMP\wm_thememenu.png")
$small.Dispose()
$big.Dispose()
Write-Output ("SHOT {0}x{1} at ({2},{3})" -f $capW, $capH, $capX, $capY)

# dismiss, restore NOTOPMOST, close
[TMS]::keybd_event(0x1B, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 200
[TMS]::keybd_event(0x1B, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 300
$null = [TMS]::SetWindowPos($hm, [IntPtr](-2), 0, 0, 0, 0, 0x0003)
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm) { $null = $p.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Write-Output MENU_SHOT_DONE
