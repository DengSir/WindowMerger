# ASCII-only: diagnose notepad PID after Start-Process -PassThru.
$np = Start-Process notepad "$env:TEMP\wmt1.txt" -PassThru
Start-Sleep -Milliseconds 1500
Write-Output ("PASS_THRU_PID=" + $np.Id + " HAS_EXITED=" + $np.HasExited)
Get-Process Notepad -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output ("NOTEPAD_PROC PID=" + $_.Id + " MAINHWND=" + $_.MainWindowHandle)
}
Write-Output DIAG_DONE
