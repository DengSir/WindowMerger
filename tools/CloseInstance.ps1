# ASCII-only: gracefully close WindowMerger (WM_CLOSE via CloseMainWindow) so the
# exe is not locked for rebuild; test windows (notepad/mspaint) are force-closed.
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($p in $wm) {
    $null = $p.CloseMainWindow()
}
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1500
$left = Get-Process WindowMerger -ErrorAction SilentlyContinue
if ($left) { Write-Output "STILL_RUNNING" } else { Write-Output "CLOSED_OK" }
