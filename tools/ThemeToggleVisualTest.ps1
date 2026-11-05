# ASCII-only: theme toggle via UIA — click theme button, then invoke the
# "Light"/"Dark" menu items from the popup, screenshot after each apply.
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTTT { public int L, T, R, B; }
public static class TT {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTTT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
}
"@
[TT]::SetProcessDPIAware() | Out-Null

Get-Process WindowMerger -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Sleep -Seconds 3

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
$main = [System.Windows.Automation.AutomationElement]::FromHandle($hm)
$pid2 = $proc.Id

$zhTheme = [string][char]0x4E3B + [char]0x9898
$zhLight = [string][char]0x6D45 + [char]0x8272   # 浅色
$zhDark  = [string][char]0x6DF1 + [char]0x8272   # 深色
$btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$btns = $main.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
$themeBtn = $null
foreach ($b in $btns) {
    if ($b.Current.HelpText -and $b.Current.HelpText.StartsWith($zhTheme)) { $themeBtn = $b; break }
}
if ($themeBtn -eq $null) { Write-Output "NO_THEME_BUTTON"; exit 1 }

function Snap([string]$tag) {
    $r = New-Object RECTTT
    [TT]::GetWindowRect($hm, [ref]$r) | Out-Null
    $w = $r.R - $r.L
    $bmp = New-Object System.Drawing.Bitmap($w, ($r.B - $r.T))
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    [TT]::PrintWindow($hm, $hdc, 2) | Out-Null
    $g.ReleaseHdc($hdc)
    $g.Dispose()
    $strip = $bmp.Clone([System.Drawing.Rectangle]::new(0, 0, $w, 30), $bmp.PixelFormat)
    $strip.Save("$env:TEMP\wm_theme_$tag.png")
    $strip.Dispose()
    $bmp.Dispose()
    Write-Output ("SHOT_" + $tag)
}

function InvokeMenuItem([string]$nameSuffix) {
    Start-Sleep -Milliseconds 500
    # popup menu belongs to our process; search everything for the named menu item
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pid2)
    $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
    foreach ($w in $wins) {
        $miCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::MenuItem)
        $items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $miCond)
        foreach ($it in $items) {
            if ($it.Current.Name -and $it.Current.Name.EndsWith($nameSuffix)) {
                $inv = $it.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                $inv.Invoke()
                return $true
            }
        }
    }
    return $false
}

Snap "s0"

# open menu + invoke Light
$inv = $themeBtn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$inv.Invoke()
$ok = InvokeMenuItem $zhLight
Write-Output ("LIGHT_INVOKE=" + $ok)
Start-Sleep -Milliseconds 600
Snap "s1"

# open menu + invoke Dark
$inv = $themeBtn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$inv.Invoke()
$ok = InvokeMenuItem $zhDark
Write-Output ("DARK_INVOKE=" + $ok)
Start-Sleep -Milliseconds 600
Snap "s2"

# read config to confirm persisted
$cfg = Get-Content "$env:APPDATA\WindowMerger\config.json" -Raw | ConvertFrom-Json
Write-Output ("CONFIG_THEME=" + $cfg.Theme)

$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm) { $null = $p.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Write-Output THEME_TOGGLE_TEST_DONE
