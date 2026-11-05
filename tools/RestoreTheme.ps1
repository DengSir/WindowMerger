# ASCII-only: restore user theme setting to Auto.
$cfgPath = "$env:APPDATA\WindowMerger\config.json"
$c = Get-Content $cfgPath -Raw | ConvertFrom-Json
$c.Theme = "Auto"
$c | ConvertTo-Json | Set-Content $cfgPath
Write-Output THEME_RESTORED
