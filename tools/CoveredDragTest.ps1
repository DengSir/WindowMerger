# ASCII-only: MANUAL drag verification for the covered-pane guard (IsCoveredAtCursor).
# Prepares an empty host + an always-on-top COVER form over the RIGHT pane. You drag
# notepad by hand:
#   STEP 1: drag notepad over the COVERED right pane, release there.
#           Expected: NO glow, NO attach (drop silently ignored, like dropping outside).
#   STEP 2: drag notepad over the free LEFT pane, release.
#           Expected: glow + attach into left pane.
# Press Enter after each step; the script prints the verdict (TOOLWINDOW + pane fit).
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECC { public int L, T, R, B; }
public static class CD {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECC r);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
}
"@
[CD]::SetProcessDPIAware() | Out-Null
$GWL_EXSTYLE = -20
$WS_EX_TOOLWINDOW = 0x80

function Wait-Enter {
    while ([Console]::KeyAvailable) { $null = [Console]::ReadKey($true) }
    Write-Output "...press ENTER when done"
    while ($true) {
        while ([Console]::KeyAvailable) {
            $k = [Console]::ReadKey($true)
            if ($k.Key -eq "Enter") { return }
        }
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 50
    }
}

# cleanup
Get-Process WindowMerger -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1300

Set-Content "$env:TEMP\wmcovered.txt" "covered-drag-test"
Start-Process notepad "$env:TEMP\wmcovered.txt"
Start-Sleep -Milliseconds 1500
$np = Get-Process Notepad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $np) { Write-Output "FAIL_NO_NOTEPAD"; exit 1 }
$n = [IntPtr]$np.MainWindowHandle

Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Sleep -Seconds 3
$hp = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $hp -or $hp.MainWindowHandle -eq 0) { Write-Output "FAIL_NO_HOST"; exit 1 }
$h = [IntPtr]$hp.MainWindowHandle

$hr = New-Object RECC
[CD]::GetWindowRect($h, [ref]$hr) | Out-Null
$w = $hr.R - $hr.L

# cover form over the RIGHT pane, above the topmost host
$null = [CD]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
Start-Sleep -Milliseconds 200
$cover = New-Object System.Windows.Forms.Form
$cover.Text = "COVER"
$cover.FormBorderStyle = "None"
$cover.BackColor = [System.Drawing.Color]::Firebrick
$cover.TopMost = $true
$cover.ShowInTaskbar = $false
$cover.Bounds = New-Object System.Drawing.Rectangle ([int]($hr.L + $w * 0.55)), ([int]($hr.T + 40)), ([int]($w * 0.4)), ([int]($hr.B - $hr.T - 60))
$label = New-Object System.Windows.Forms.Label
$label.Text = "COVERED RIGHT PANE - drops here must be refused"
$label.ForeColor = [System.Drawing.Color]::White
$label.Dock = "Fill"
$label.TextAlign = "MiddleCenter"
$cover.Controls.Add($label)
$cover.Show()
[System.Windows.Forms.Application]::DoEvents()

Write-Output ("HOST ({0},{1})-({2},{3})  notepad hwnd=0x{4:X}" -f $hr.L, $hr.T, $hr.R, $hr.B, $n)
Write-Output "STEP 1: drag notepad by its title bar over the RED right pane and release there."
Wait-Enter
$ex = [CD]::GetWindowLong($n, $GWL_EXSTYLE)
if (($ex -band $WS_EX_TOOLWINDOW) -ne 0) {
    Write-Output "STEP1 FAIL: notepad got docked despite covered pane"
} else {
    Write-Output "STEP1 PASS: notepad not docked (covered drop ignored)"
}

Write-Output "STEP 2: drag notepad over the free LEFT pane and release there."
Wait-Enter
$ex = [CD]::GetWindowLong($n, $GWL_EXSTYLE)
$nr = New-Object RECC
[CD]::GetWindowRect($n, [ref]$nr) | Out-Null
$inLeft = ($nr.L -gt $hr.L - 30) -and ($nr.L -lt $hr.L + $w * 0.5) -and ($nr.T -gt $hr.T) -and ($nr.B -le $hr.B + 30)
if (($ex -band $WS_EX_TOOLWINDOW) -ne 0 -and $inLeft) {
    Write-Output ("STEP2 PASS: notepad docked into left pane rect=({0},{1})-({2},{3})" -f $nr.L, $nr.T, $nr.R, $nr.B)
} else {
    Write-Output ("STEP2 FAIL: toolwindow={0} inLeft={1} rect=({2},{3})-({4},{5})" -f (($ex -band $WS_EX_TOOLWINDOW) -ne 0), $inLeft, $nr.L, $nr.T, $nr.R, $nr.B)
}

# cleanup: graceful host close releases notepad; restore NOTOPMOST
$null = [CD]::SetWindowPos($h, [IntPtr](-2), 0, 0, 0, 0, 0x0003)
$cover.Close()
$null = $hp.CloseMainWindow()
Start-Sleep -Milliseconds 1500
Get-Process Notepad -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output COVERED_DRAG_TEST_DONE
