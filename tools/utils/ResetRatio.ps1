# ASCII-only: reset divider ratio to 0.5 in config.json.
$cfgPath = "$env:APPDATA\WindowMerger\config.json"
$c = Get-Content $cfgPath -Raw | ConvertFrom-Json
Write-Output ("CURRENT_RATIO=" + $c.Ratio)
$c.Ratio = 0.5
$c | ConvertTo-Json | Set-Content $cfgPath
Write-Output RATIO_RESET_DONE
