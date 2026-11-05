# ASCII-only: real Alt+Tab z-order repro.
# Scenario: host (merged notepad+mspaint) fully covered by a maximized mspaint,
# Alt+Tab back to host, probe whether child windows rise above the cover window.
# Probe hits: TOPBAR = host chrome (opaque), LEFT/RIGHT = pane centers.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PTZ { public int X, Y; }
public struct RECTZ { public int L, T, R, B; }
public static class AZ {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTZ p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTZ r);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int m);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetTopWindow(IntPtr h);
}
"@
[AZ]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [AZ]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

function AltTabOnce {
    [AZ]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)   # ALT down
    Start-Sleep -Milliseconds 100
    [AZ]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)   # TAB down
    Start-Sleep -Milliseconds 80
    [AZ]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)   # TAB up
    Start-Sleep -Milliseconds 600
    [AZ]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)   # ALT up -> switch happens
    Start-Sleep -Milliseconds 600
}

function Probe([string]$tag) {
    $hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
    if ($hm -eq [IntPtr]::Zero) { Write-Output "$tag NO_HOST"; return }
    $hr = New-Object RECTZ
    [AZ]::GetWindowRect($hm, [ref]$hr) | Out-Null
    $fg = ProcOf ([AZ]::GetForegroundWindow())

    $avail = $hr.R - $hr.L - 4 - 8
    $p1 = New-Object PTZ; $p1.X = [int](($hr.L + $hr.R) / 2);        $p1.Y = $hr.T + 14
    $p2 = New-Object PTZ; $p2.X = [int]($hr.L + 2 + $avail * 0.35); $p2.Y = [int](($hr.T + $hr.B) / 2)
    $p3 = New-Object PTZ; $p3.X = [int]($hr.L + 2 + $avail * 0.75); $p3.Y = [int](($hr.T + $hr.B) / 2)
    $top = ProcOf ([AZ]::WindowFromPoint($p1))
    $left = ProcOf ([AZ]::WindowFromPoint($p2))
    $right = ProcOf ([AZ]::WindowFromPoint($p3))
    Write-Output ("{0}: FG={1} TOPBAR={2} LEFT={3} RIGHT={4}" -f $tag, $fg, $top, $left, $right)
}

function ZDump([string]$tag) {
    Write-Output "--- z-order $tag (top first, visible only) ---"
    $cur = [AZ]::GetTopWindow([IntPtr]::Zero)
    for ($i = 0; $i -lt 40 -and $cur -ne [IntPtr]::Zero; $i++) {
        if ([AZ]::IsWindowVisible($cur)) {
            $t = New-Object System.Text.StringBuilder 96
            [AZ]::GetWindowText($cur, $t, 96) | Out-Null
            $r = New-Object RECTZ
            [AZ]::GetWindowRect($cur, [ref]$r) | Out-Null
            $ic = [AZ]::IsIconic($cur)
            Write-Output ("Z{0,-2} {1,-12} iconic={2} rect=({3},{4}) [{5}]" -f $i, (ProcOf $cur), $ic, $r.L, $r.T, $t.ToString())
        }
        $cur = [AZ]::GetWindow($cur, 2)   # GW_HWNDNEXT
    }
}

# 1. cleanup
Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

# 2. test windows
Set-Content "$env:TEMP\wmt1.txt" "z-repro-1"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 700
Start-Process mspaint
Start-Sleep -Milliseconds 1500
$mp = (Get-Process mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle
if ($mp -eq 0 -or $null -eq $mp) { Write-Output "FAIL no-mspaint"; exit 1 }

# 3. host with CLI attach (targets must exist before host starts)
$exe = "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Process $exe -ArgumentList "--left", "notepad", "--right", "mspaint"
Start-Sleep -Seconds 4
Probe "STEP0_ATTACHED"

# maximize mspaint so it fully covers the host, and make it foreground via ALT trick
$SW_MAXIMIZE = 3
[AZ]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
$null = [AZ]::SetForegroundWindow($mp)
[AZ]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 300
$null = [AZ]::ShowWindow($mp, $SW_MAXIMIZE)
Start-Sleep -Milliseconds 800
Probe "STEP1_COVERED_BY_MAX_MSPAINT"

# 4. Alt+Tab back to host, probe immediately and after healing window
AltTabOnce
Start-Sleep -Milliseconds 200
Probe "STEP2_BACK_NOW"
Start-Sleep -Milliseconds 1500
Probe "STEP3_BACK_1_7S"

# 5. second full cycle
AltTabOnce    # -> mspaint
Start-Sleep -Milliseconds 400
Probe "STEP4_COVERED_AGAIN"
AltTabOnce    # -> host
Start-Sleep -Milliseconds 200
Probe "STEP5_BACK2_NOW"
Start-Sleep -Milliseconds 1500
Probe "STEP6_BACK2_1_7S"

ZDump "FINAL"
Write-Output REPRO_DONE
