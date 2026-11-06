# ASCII-only: verify the create-shortcut button. Attach notepad+mspaint via CLI,
# UIA-invoke the _shortcutButton, then read the fresh .lnk from the Desktop via
# WScript.Shell and assert TargetPath/Arguments. Deletes the .lnk afterwards.
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"

# cleanup
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1300

# target windows
Set-Content "$env:TEMP\wmsc.txt" "shortcut-test"
Start-Process notepad "$env:TEMP\wmsc.txt"
Start-Sleep -Milliseconds 700
Start-Process mspaint
Start-Sleep -Milliseconds 1500

Start-Process $exe -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) { Write-Output "FAIL_NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle

# UIA invoke the shortcut button (x:Name -> AutomationId)
$root = [Windows.Automation.AutomationElement]::FromHandle($hm)
$cond = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::AutomationIdProperty, "_shortcutButton")
$btn = $root.FindFirst([Windows.Automation.TreeScope]::Descendants, $cond)
if (-not $btn) { Write-Output "FAIL_NO_BUTTON"; exit 1 }
$inv = $btn.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern)
$inv.Invoke()
Start-Sleep -Seconds 2

# locate the fresh lnk: filename prefix is the Chinese app name, built from char codes
$prefix = -join [char[]](0x7A97, 0x53E3, 0x5408, 0x5E76)   # "WindowMerger" Chinese word
$desktop = [Environment]::GetFolderPath("DesktopDirectory")
$lnk = Get-ChildItem $desktop -Filter "*.lnk" | Where-Object { $_.Name.StartsWith($prefix) -and $_.LastWriteTime -gt (Get-Date).AddMinutes(-2) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $lnk) { Write-Output "FAIL_NO_LNK"; exit 1 }

$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk.FullName)
Write-Output ("TARGET=" + $s.TargetPath)
Write-Output ("ARGS=" + $s.Arguments)
Write-Output ("ICON=" + $s.IconLocation)
$okArgs = ($s.Arguments -match '--left\s+"?notepad"?') -and ($s.Arguments -match '--right\s+"?mspaint"?')
$okTarget = $s.TargetPath -like "*WindowMerger*.exe"
if ($okArgs -and $okTarget) { Write-Output "PASS_SHORTCUT" } else { Write-Output "FAIL_CONTENT" }

Remove-Item $lnk.FullName -Force

# cleanup
$null = $proc.CloseMainWindow()
Start-Sleep -Milliseconds 1500
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output SHORTCUT_TEST_DONE
