# ASCII-only: visual check of empty-pane placeholder hints. Phase 1: plain host
# (both panes show fill + hint). Phase 2: CLI-attach notepad to the left pane
# (left hint must disappear, notepad visible through the transparent pane; right
# hint stays). Topmost + screen capture, NOTOPMOST restored, hosts closed at end.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTN { public int L, T, R, B; }
public static class HN {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTN r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
}
"@
[HN]::SetProcessDPIAware() | Out-Null

$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"

function Shot-Host([IntPtr]$h, [string]$tag) {
    $r = New-Object RECTN
    [HN]::GetWindowRect($h, [ref]$r) | Out-Null
    $null = [HN]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
    Start-Sleep -Milliseconds 400
    $big = New-Object System.Drawing.Bitmap(2560, 1440)
    $g = [System.Drawing.Graphics]::FromImage($big)
    $g.CopyFromScreen(0, 0, 0, 0, $big.Size)
    $g.Dispose()
    $w = $r.R - $r.L; $hh = $r.B - $r.T
    $small = $big.Clone([System.Drawing.Rectangle]::new($r.L, $r.T, $w, $hh), $big.PixelFormat)
    $small.Save("$env:TEMP\wm_hint_$tag.png")
    $small.Dispose()
    $big.Dispose()
    $null = [HN]::SetWindowPos($h, [IntPtr](-2), 0, 0, 0, 0, 0x0003)
    Write-Output ("SHOT_" + $tag)
}

# cleanup
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1300

# phase 1: empty host
Start-Process $exe
Start-Sleep -Seconds 3
$a = Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $a) { Write-Output "NO_HOST"; exit 1 }
Shot-Host ([IntPtr]$a.MainWindowHandle) "empty"
$null = $a.CloseMainWindow()
Start-Sleep -Milliseconds 1500

# phase 2: left pane occupied
Start-Process notepad "$env:TEMP\wmhint.txt" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmhint.txt" "hint-test"
Start-Process notepad "$env:TEMP\wmhint.txt"
Start-Sleep -Milliseconds 1500
Start-Process $exe -ArgumentList "--left", "notepad"
Start-Sleep -Seconds 4
$b = Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $b) { Write-Output "NO_HOST_2"; exit 1 }
Shot-Host ([IntPtr]$b.MainWindowHandle) "leftoccupied"

# cleanup
$null = $b.CloseMainWindow()
Start-Sleep -Milliseconds 1500
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output HINT_SHOT_DONE
