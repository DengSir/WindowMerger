# ASCII-only: hover the WindowMerger taskbar button and capture the thumbnail popup.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type 'using System; using System.Runtime.InteropServices; public static class HV { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y); [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }'
[HV]::SetProcessDPIAware() | Out-Null

# find taskbar (Shell_TrayWnd) then our button by name
$root = [System.Windows.Automation.AutomationElement]::RootElement
$taskbar = $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "Shell_TrayWnd")))
if ($taskbar -eq $null) { Write-Output "NO_TASKBAR"; exit 1 }

$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "窗口合并 WindowMerger")
$btn = $taskbar.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if ($btn -eq $null) {
    # fallback: substring search over all buttons
    $all = $taskbar.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($e in $all) {
        if ($e.Current.Name -match "WindowMerger") { $btn = $e; break }
    }
}
if ($btn -eq $null) { Write-Output "NO_BUTTON"; exit 1 }

$rect = $btn.Current.BoundingRectangle
$cx = [int]($rect.X + $rect.Width / 2)
$cy = [int]($rect.Y + $rect.Height / 2)
Write-Output ("BUTTON at " + $cx + "," + $cy + " name=[" + $btn.Current.Name + "]")

# hover and wait for thumbnail popup
[HV]::SetCursorPos($cx, $cy) | Out-Null
Start-Sleep -Milliseconds 1500

# capture region above the taskbar button (thumbnail popup area)
$w = 620; $h = 420
$bx = [Math]::Max(0, $cx - [int]($w / 2))
$by = [Math]::Max(0, $cy - $h - 10)
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bx, $by, 0, 0, $bmp.Size)
$g.Dispose()
$big = New-Object System.Drawing.Bitmap(1240, 840)
$g2 = [System.Drawing.Graphics]::FromImage($big)
$g2.InterpolationMode = 'NearestNeighbor'
$g2.DrawImage($bmp, 0, 0, 1240, 840)
$g2.Dispose()
$big.Save('C:\Users\Dencer\AppData\Local\Temp\wm_hover.png')
$big.Dispose()
$bmp.Dispose()

# move cursor away so the popup closes
[HV]::SetCursorPos(1280, 1400) | Out-Null
Write-Output HOVER_SHOT_OK
