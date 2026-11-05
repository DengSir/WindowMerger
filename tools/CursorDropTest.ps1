# ASCII-only: cursor-based drop verification.
# Host fresh (no config) at (640,296)-(1920,1096), ratio 0.5.
# Notepad moved to (300,300) 500x400, grabbed by title at (320,310).
# CASE B (must NOT attach): drag to (500,700). Cursor ends OUTSIDE host (x=500<640)
#   but window center lands (730,890) INSIDE left pane -> old center-logic would
#   attach; new cursor-logic must not. Verify: no TOOLWINDOW, rect stays.
# CASE A (must attach): drag notepad title to left-pane center (959,696).
#   Verify: TOOLWINDOW set, window resized to pane, LEFT_HIT=Notepad.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTX { public int L, T, R, B; }
public static class CB {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTX r);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTX p);
    public struct PTX { public int X, Y; }
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
}
"@
[CB]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [CB]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}
$script:npHandle = [IntPtr]::Zero
function NotepadState([string]$tag) {
    $np = (Get-Process Notepad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1)
    if (-not $np) { Write-Output "$tag NO_NOTEPAD"; $script:npHandle = [IntPtr]::Zero; return }
    $script:npHandle = [IntPtr]$np.MainWindowHandle
    $r = New-Object RECTX
    [CB]::GetWindowRect($script:npHandle, [ref]$r) | Out-Null
    $tool = (([CB]::GetWindowLong($script:npHandle, -20) -band 0x80) -ne 0)
    Write-Output ("{0}: tool={1} rect=({2},{3})-({4},{5})" -f $tag, $tool, $r.L, $r.T, $r.R, $r.B)
}

# 1. fresh env
Get-Process WindowMerger, Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item "$env:APPDATA\WindowMerger\config.json" -ErrorAction SilentlyContinue
Set-Content "$env:TEMP\wmt1.txt" "cursor-drop"
Start-Process notepad "$env:TEMP\wmt1.txt"
Start-Sleep -Milliseconds 1500
Start-Process "D:\AddOns\WindowMerger\bin\Release\net10.0-windows\WindowMerger.exe"
Start-Sleep -Seconds 4
$hm = (Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle
if ($hm -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECTX
[CB]::GetWindowRect([IntPtr]$hm, [ref]$hr) | Out-Null
Write-Output ("HOST ({0},{1})-({2},{3})" -f $hr.L, $hr.T, $hr.R, $hr.B)

function FocusNotepad([IntPtr]$h) {
    for ($try = 0; $try -lt 3; $try++) {
        [CB]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
        [CB]::SetForegroundWindow($h) | Out-Null
        [CB]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 400
        $p = New-Object CB+PTX
        $p.X = 320; $p.Y = 310
        if ((ProcOf ([CB]::WindowFromPoint($p))) -eq "Notepad") { return $true }
    }
    return $false
}

# position notepad at (300,300) 500x400 (NOACTIVATE: notepad stays foreground above other apps)
$np = Get-Process Notepad | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$nh = [IntPtr]$np.MainWindowHandle
[CB]::SetWindowPos($nh, [IntPtr]::Zero, 300, 300, 500, 400, 0x0014) | Out-Null   # NOZORDER|NOACTIVATE
Start-Sleep -Milliseconds 500
NotepadState "INIT" | Out-Null

# 2. CASE B: drag title (320,310) -> (500,700). Cursor outside host, center inside pane.
if (-not (FocusNotepad $nh)) { Write-Output "SKIP_COVERED"; exit 1 }
[CB]::SetCursorPos(320, 310) | Out-Null
Start-Sleep -Milliseconds 150
[CB]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)   # down
Start-Sleep -Milliseconds 150
for ($i = 1; $i -le 20; $i++) {
    $x = 320 + [int]((500 - 320) * $i / 20)
    $y = 310 + [int]((700 - 310) * $i / 20)
    [CB]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds 25
}
Start-Sleep -Milliseconds 200
[CB]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)   # up
Start-Sleep -Milliseconds 1000
NotepadState "CASE_B_NO_ATTACH_EXPECTED"

# 3. CASE A: notepad now at (480,690). Drag title (500,700) -> left pane center (959,696).
# verify the grab point hits notepad (it moved in case B); refocus and re-check there
$grabOk = $false
for ($try = 0; $try -lt 3; $try++) {
    [CB]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
    [CB]::SetForegroundWindow($nh) | Out-Null
    [CB]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 400
    $p = New-Object CB+PTX
    $p.X = 500; $p.Y = 700
    if ((ProcOf ([CB]::WindowFromPoint($p))) -eq "Notepad") { $grabOk = $true; break }
}
if (-not $grabOk) { Write-Output "SKIP_CASE_A_COVERED"; NotepadState "FINAL_STATE"; exit 1 }
[CB]::SetCursorPos(500, 700) | Out-Null
Start-Sleep -Milliseconds 150
[CB]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150
for ($i = 1; $i -le 20; $i++) {
    $x = 500 + [int]((959 - 500) * $i / 20)
    $y = 700 + [int]((696 - 700) * $i / 20)
    [CB]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds 25
}
Start-Sleep -Milliseconds 200
[CB]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 1000
NotepadState "CASE_A_ATTACH_EXPECTED"
if ($script:npHandle -ne [IntPtr]::Zero) {
    $p = New-Object CB+PTX
    $p.X = 959; $p.Y = 696
    Write-Output ("LEFT_HIT=" + (ProcOf ([CB]::WindowFromPoint($p))))
}

# 4. cleanup
$wm = Get-Process WindowMerger -ErrorAction SilentlyContinue
foreach ($proc in $wm) { $null = $proc.CloseMainWindow() }
Start-Sleep -Milliseconds 1200
Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output CURSOR_DROP_TEST_DONE
