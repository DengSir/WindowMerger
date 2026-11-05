# ASCII-only: gracefully close WindowMerger only (WM_CLOSE via CloseMainWindow),
# leave other applications untouched.
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm) {
    $null = $p.CloseMainWindow()
}
Start-Sleep -Milliseconds 1500
if (Get-Process WindowMerger -ErrorAction SilentlyContinue) { Write-Output "STILL_RUNNING" } else { Write-Output "CLOSED_OK" }
