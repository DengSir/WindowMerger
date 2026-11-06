# ASCII-only: divider hover check — vertical strip around divider x at mid height.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTHD { public int L, T, R, B; }
public static class HVD {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTHD r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
[HVD]::SetProcessDPIAware() | Out-Null

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
$hr = New-Object RECTHD
[HVD]::GetWindowRect($hm, [ref]$hr) | Out-Null
$w = $hr.R - $hr.L; $h = $hr.B - $hr.T
$ratio = 0.5
try { $ratio = (Get-Content "$env:APPDATA\WindowMerger\config.json" -Raw | ConvertFrom-Json).Ratio } catch {}
Write-Output ("RATIO=" + $ratio)
$avail = $w - 4 - 8
$divX = [int]($hr.L + 2 + $avail * $ratio + 4)
$null = [HVD]::SetWindowPos($hm, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
Start-Sleep -Milliseconds 300

function Snap([string]$tag) {
    # ensure the cursor point actually hits our divider (retry: topmost can be
    # defeated by the user's active window)
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PTHD { public int X, Y; }
public static class HVD2 {
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTHD p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
"@
    $ok = $false
    for ($try = 0; $try -lt 3 -and -not $ok; $try++) {
        $null = [HVD]::SetWindowPos($hm, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
        Start-Sleep -Milliseconds 300
        $null = [HVD]::SetCursorPos($divX, [int]($h / 2))
        Start-Sleep -Milliseconds 400
        $p = New-Object PTHD
        $p.X = $divX; $p.Y = [int]($h / 2)
        $hit = [HVD2]::WindowFromPoint($p)
        $hitPid = 0
        [HVD2]::GetWindowThreadProcessId($hit, [ref]$hitPid) | Out-Null
        if ($hitPid -eq $proc.Id) { $ok = $true }
    }
    if (-not $ok) { Write-Output ("{0}: SKIP_COVERED" -f $tag); return }
    $bmp = New-Object System.Drawing.Bitmap($w, $h)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    [HVD]::PrintWindow($hm, $hdc, 2) | Out-Null
    $g.ReleaseHdc($hdc)
    $g.Dispose()
    $crop = $bmp.Clone([System.Drawing.Rectangle]::new([int]($divX - $hr.L) - 30, 200, 60, 300), $bmp.PixelFormat)
    $crop.Save("$env:TEMP\wm_divhover_$tag.png")
    $crop.Dispose()
    # sample the divider pixel color at mid height
    $c = $bmp.GetPixel([int]($divX - $hr.L), [int]($h / 2))
    Write-Output ("{0}: divider RGB=({1},{2},{3})" -f $tag, $c.R, $c.G, $c.B)
    $bmp.Dispose()
}

[HVD]::SetCursorPos(6, 700) | Out-Null
Snap "base"
[HVD]::SetCursorPos($divX, [int]($h / 2)) | Out-Null
Snap "hover"
[HVD]::SetCursorPos(6, 700) | Out-Null
Snap "left"

$null = [HVD]::SetWindowPos($hm, [IntPtr](-2), 0, 0, 0, 0, 0x0003)
Write-Output DIVIDER_HOVER_TEST_DONE
