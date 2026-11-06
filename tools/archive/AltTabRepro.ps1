# ASCII-only: real Alt+Tab input repro — switch away, switch back via title click, probe each step.
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct PTA { public int X, Y; }
public struct RECTA { public int L, T, R, B; }
public static class AR {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PTA p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTA r);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
}
"@
[AR]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [AR]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}
function Probe([string]$tag) {
    $hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
    if ($hm -eq [IntPtr]::Zero) { Write-Output "$tag NO_HOST"; return }
    $hr = New-Object RECTA
    [AR]::GetWindowRect($hm, [ref]$hr) | Out-Null
    $p = New-Object AR+PTA
    $p.X = [int](($hr.L + $hr.R) / 4); $p.Y = [int](($hr.T + $hr.B) / 2)
    $h = [AR]::WindowFromPoint($p)
    $fg = [AR]::GetForegroundWindow()
    Write-Output ("{0}: FG={1} LEFT_HIT={2}" -f $tag, (ProcOf $fg), (ProcOf $h))
}

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECTA
[AR]::GetWindowRect($hm, [ref]$hr) | Out-Null
Probe "STEP0_INITIAL"

# switch away with real ALT+TAB
[AR]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)   # ALT down
Start-Sleep -Milliseconds 100
[AR]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)   # TAB down
Start-Sleep -Milliseconds 80
[AR]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)   # TAB up
Start-Sleep -Milliseconds 600
[AR]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)   # ALT up
Start-Sleep -Milliseconds 1200
Probe "STEP1_AFTER_ALT_TAB_AWAY"

# switch back to host with real ALT+TAB (one more cycle)
[AR]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 100
[AR]::keybd_event(0x09, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[AR]::keybd_event(0x09, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 600
[AR]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 1500
Probe "STEP2_AFTER_ALT_TAB_BACK"

# click host title to force activation
$tx = [int]($hr.L + ($hr.R - $hr.L) * 0.3); $ty = $hr.T + 14
[AR]::SetCursorPos($tx, $ty) | Out-Null
Start-Sleep -Milliseconds 150
[AR]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[AR]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 900
Probe "STEP3_AFTER_TITLE_CLICK"

# dump z-chain below and above host
$cur = $hm
for ($i = 1; $i -le 3; $i++) {
    $cur = [AR]::GetWindow($cur, 3)
    if ($cur -eq [IntPtr]::Zero) { break }
    $procId = 0
    [AR]::GetWindowThreadProcessId($cur, [ref]$procId) | Out-Null
    $pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
    $vis = [AR]::IsWindowVisible($cur)
    Write-Output ("ABOVE+{0}: {1} vis={2}" -f $i, $pn, $vis)
}
$cur = $hm
for ($i = 1; $i -le 3; $i++) {
    $cur = [AR]::GetWindow($cur, 2)
    if ($cur -eq [IntPtr]::Zero) { break }
    $procId = 0
    [AR]::GetWindowThreadProcessId($cur, [ref]$procId) | Out-Null
    $pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
    $vis = [AR]::IsWindowVisible($cur)
    Write-Output ("BELOW+{0}: {1} vis={2}" -f $i, $pn, $vis)
}
