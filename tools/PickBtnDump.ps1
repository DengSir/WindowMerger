# ASCII-only: dump pick-button glyph codepoints via UIA + 4x zoom capture of the two buttons.
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTU2 { public int L, T, R, B; }
public static class U2 {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTU2 r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
}
"@

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$main = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$proc.MainWindowHandle)
$btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$btns = $main.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)

$i = 0
foreach ($b in $btns) {
    $n = $b.Current.Name
    if ($n -and $n.Length -gt 0) {
        $cp = ($n.ToCharArray() | ForEach-Object { "U+{0:X4}" -f [int]$_ }) -join " "
        Write-Output ("BTN[{0}] name-cps: {1}" -f $i, $cp)
    }
    $i++
}

# 4x zoom capture of the two pick buttons region (they sit right after the app label)
$hm = [IntPtr]$proc.MainWindowHandle
$r = New-Object RECTU2
[U2]::GetWindowRect($hm, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap(($r.R - $r.L), ($r.B - $r.T))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[U2]::PrintWindow($hm, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc)
$g.Dispose()
Add-Type -AssemblyName System.Drawing
$crop = $bmp.Clone([System.Drawing.Rectangle]::new(155, 0, 120, 30), $bmp.PixelFormat)
$zoom = New-Object System.Drawing.Bitmap(480, 120)
$gz = [System.Drawing.Graphics]::FromImage($zoom)
$gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$gz.DrawImage($crop, 0, 0, 480, 120)
$gz.Dispose()
$zoom.Save("$env:TEMP\wm_pickbtns_zoom.png")
$zoom.Dispose()
$crop.Dispose()
$bmp.Dispose()
Write-Output PICK_ZOOM_DONE
