# ASCII-only: UIA-only theme dropdown verification (no injected input, works
# even on a locked desktop).
# 1) save original Theme from config.json
# 2) launch app, open the theme menu by invoking the theme button via UIA
# 3) read the 3 menu items (order: auto, dark, light), print name codepoints
# 4) invoke dark -> config Theme == Dark; re-open -> dark item marked U+2713
# 5) invoke original mode to restore config, then graceful close
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$cfg = "$env:APPDATA\WindowMerger\config.json"
$origTheme = "Auto"
if (Test-Path $cfg) {
    try { $origTheme = (Get-Content $cfg -Raw | ConvertFrom-Json).Theme } catch {}
}
Write-Output ("ORIG_THEME=" + $origTheme)

# theme tooltip starts with these two codepoints (keep script ASCII-only)
$zhTheme = [string][char]0x4E3B + [char]0x9898   # "zhu ti"
$chk = [string][char]0x2713                      # check mark

function NameCodepoints($e) {
    $n = $e.Current.Name
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $n.ToCharArray()) { [void]$sb.AppendFormat("U+{0:X4} ", [int]$ch) }
    return $sb.ToString()
}

function InvokeElem($e) {
    $inv = $e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $inv.Invoke()
}

function ReadCfgTheme {
    if (Test-Path $cfg) {
        try { return (Get-Content $cfg -Raw | ConvertFrom-Json).Theme } catch { return "READ_FAIL" }
    }
    return "NO_FILE"
}

function GetMenuItems($pid2) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pid2)
    $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
    $items = @()
    $miCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::MenuItem)
    foreach ($w in $wins) {
        $found = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $miCond)
        foreach ($it in $found) { $items += $it }
    }
    return $items
}

# launch fresh instance
$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Process $exe
Start-Sleep -Seconds 3

$proc = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc -or $proc.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hm = [IntPtr]$proc.MainWindowHandle
$pid2 = $proc.Id
$main = [System.Windows.Automation.AutomationElement]::FromHandle($hm)

# find the theme caption button: 8 caption buttons in row order,
# index 4 = theme; cross-check via HelpText tooltip prefix
$btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$btns = $main.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
Write-Output ("BUTTONS=" + $btns.Count)
if ($btns.Count -lt 5) { Write-Output "NO_THEME_BUTTON"; exit 1 }
$themeBtn = $btns[4]
for ($i = 0; $i -lt $btns.Count; $i++) {
    $help = $btns[$i].Current.HelpText
    if ($help -and $help.StartsWith($zhTheme)) { $themeBtn = $btns[$i]; Write-Output ("THEME_BTN_BY_TOOLTIP idx=" + $i) }
}

# open menu, read items
InvokeElem $themeBtn
Start-Sleep -Milliseconds 800
$items = GetMenuItems $pid2
Write-Output ("ITEMS_FOUND=" + $items.Count)
for ($i = 0; $i -lt $items.Count; $i++) {
    Write-Output ("ITEM[{0}] {1}" -f $i, (NameCodepoints $items[$i]))
}

if ($items.Count -ge 3) {
    InvokeElem $items[1]   # dark
    Start-Sleep -Milliseconds 600
    Write-Output ("THEME_AFTER_DARK=" + (ReadCfgTheme))

    InvokeElem $themeBtn   # reopen
    Start-Sleep -Milliseconds 800
    $items2 = GetMenuItems $pid2
    Write-Output ("ITEMS2_FOUND=" + $items2.Count)
    for ($i = 0; $i -lt $items2.Count; $i++) {
        $first = (NameCodepoints $items2[$i]).Trim().Split(" ")[0]
        Write-Output ("ITEM2[{0}] first={1}" -f $i, $first)
    }

    # restore original mode: 0=Auto 1=Dark 2=Light
    $map = @{ "Auto" = 0; "Dark" = 1; "Light" = 2 }
    $idx = 0
    if ($map.ContainsKey($origTheme)) { $idx = $map[$origTheme] }
    if ($items2.Count -ge 3) {
        InvokeElem $items2[$idx]
        Start-Sleep -Milliseconds 600
        Write-Output ("THEME_RESTORED=" + (ReadCfgTheme))
    }
} else {
    Write-Output "MENU_NOT_FOUND"
}

# graceful close
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm) { $null = $p.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
if (Get-Process WindowMerger -ErrorAction SilentlyContinue) { Write-Output "APP_STILL_RUNNING" } else { Write-Output "APP_CLOSED" }
Write-Output THEME_UIA_TEST_DONE
