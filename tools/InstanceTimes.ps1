# ASCII-only: show WindowMerger instance start times.
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output ("PID={0} START={1}" -f $_.Id, $_.StartTime.ToString("HH:mm:ss"))
}
