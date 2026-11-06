# ASCII-only: set theme mode in config.json.
param([string]$Mode = "Auto")
$cfgPath = "$env:APPDATA\WindowMerger\config.json"
$c = Get-Content $cfgPath -Raw | ConvertFrom-Json
$c.Theme = $Mode
$c | ConvertTo-Json | Set-Content $cfgPath
Write-Output ("THEME_SET=" + $Mode)
