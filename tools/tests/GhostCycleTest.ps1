# ASCII-only: catch the ghost taskbar button during attach/release cycles (v2).
# Dumps via z-chain iteration (EnumWindows delegate output is swallowed in PS).
# After each release: (a) UIA taskbar buttons, (b) titled+unowned+non-toolwindow
# top-level windows with vis/iconic/cloaked/rect — a taskbar entry whose window
# is hidden/offscreen = the ghost. Final: kill all test apps, re-dump buttons —
# a button for a dead app = stale shell entry (the click-does-nothing ghost).
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct RECTG { public int L, T, R, B; }
public static class GH3 {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr GetTopWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTG r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out int v, int s);
}
"@
[GH3]::SetProcessDPIAware() | Out-Null

function DumpWindows([string]$tag) {
    Write-Output "--- titled unowned non-toolwindows $tag ---"
    $cur = [GH3]::GetTopWindow([IntPtr]::Zero)
    for ($i = 0; $i -lt 400 -and $cur -ne [IntPtr]::Zero; $i++) {
        $ex = [GH3]::GetWindowLong($cur, -20)
        $owned = [GH3]::GetWindow($cur, 4) -ne [IntPtr]::Zero
        if ((($ex -band 0x80) -eq 0) -and -not $owned) {
            $tb = New-Object System.Text.StringBuilder 64
            [GH3]::GetWindowText($cur, $tb, 64) | Out-Null
            if ($tb.Length -gt 0) {
                $procId = 0
                [GH3]::GetWindowThreadProcessId($cur, [ref]$procId) | Out-Null
                $pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
                $sb = New-Object System.Text.StringBuilder 48
                [GH3]::GetClassName($cur, $sb, 48) | Out-Null
                $r = New-Object RECTG
                [GH3]::GetWindowRect($cur, [ref]$r) | Out-Null
                $vis = [GH3]::IsWindowVisible($cur)
                $ic = [GH3]::IsIconic($cur)
                $cl = 0
                [GH3]::DwmGetWindowAttribute($cur, 14, [ref]$cl, 4) | Out-Null
                $off = ($r.R -le -30000 -or $r.L -le -30000)
                Write-Output ("0x{0:X} {1,-9} vis={2,-5} iconic={3,-5} cloaked={4} off={5} rect=({6},{7})-({8},{9}) class={10} title=[{11}]" -f $cur.ToInt64(), $pn, $vis, $ic, $cl, $off, $r.L, $r.T, $r.R, $r.B, $sb.ToString(), $tb.ToString())
            }
        }
        $cur = [GH3]::GetWindow($cur, 2)
    }
}

function DumpTaskbarButtons([string]$tag) {
    Write-Output "--- taskbar buttons $tag ---"
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $taskbar = $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "Shell_TrayWnd")))
    if ($taskbar -eq $null) { Write-Output "NO_TASKBAR"; return }
    $btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    $btns = $taskbar.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
    foreach ($b in $btns) {
        $n = $b.Current.Name
        if ($n -and $n.Length -gt 0 -and $b.Current.AutomationId -like "Appid:*") {
            Write-Output ("BTN [{0}]" -f $n)
        }
    }
}

for ($round = 1; $round -le 5; $round++) {
    Write-Output ("===== ROUND " + $round + " =====")
    Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 700
    Set-Content "$env:TEMP\wmt1.txt" "ghost-r$round"
    Start-Process notepad "$env:TEMP\wmt1.txt"
    Start-Sleep -Milliseconds 600
    Start-Process mspaint
    Start-Sleep -Milliseconds 1400
    Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe" -ArgumentList "--left", "notepad", "--right", "mspaint"
    Start-Sleep -Seconds 4
    $proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; continue }
    $main = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$proc.MainWindowHandle)
    $btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    $btns = $main.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
    if ($btns.Count -lt 4) { Write-Output "NO_RELEASE_BTN"; continue }
    $inv = $btns[3].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $inv.Invoke()
    Start-Sleep -Milliseconds 1500
    DumpTaskbarButtons "R$round"
    DumpWindows "R$round"
}

Write-Output "===== FINAL: kill test apps, check for stale buttons ====="
Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 2500
DumpTaskbarButtons "AFTER_KILL"
Write-Output GHOST_CYCLE2_DONE
