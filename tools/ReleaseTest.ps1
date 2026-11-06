# ASCII-only: release-path verification — invoke release-all, windows must lose
# TOOLWINDOW and stay intact (AttachedChild.Restore works).
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class RV {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
}
"@
[RV]::SetProcessDPIAware() | Out-Null

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$main = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$proc.MainWindowHandle)

$btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$btns = $main.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
if ($btns.Count -lt 4) { Write-Output "NO_RELEASE_BTN"; exit 1 }
$inv = $btns[3].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$inv.Invoke()
Start-Sleep -Milliseconds 1200

Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    $tool = (([RV]::GetWindowLong($_.MainWindowHandle, -20) -band 0x80) -ne 0)
    Write-Output ("{0} tool={1}" -f $_.ProcessName, $tool)
}
Write-Output RELEASE_TEST_DONE
