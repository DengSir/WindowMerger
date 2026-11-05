# ASCII-only: reproduce "switch away then back" and probe pane state after each step.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PT9 { public int X, Y; }
public static class RS {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PT9 p);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
"@
[RS]::SetProcessDPIAware() | Out-Null

function ProcOf([IntPtr]$h) {
    $procId = 0
    [RS]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
}

$hm = [IntPtr]((Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowHandle)
if ($hm -eq [IntPtr]::Zero) { Write-Output "NO_HOST"; exit 1 }

function Probe([string]$tag) {
    $p = New-Object PT9
    $p.X = 700; $p.Y = 700
    $h = [RS]::WindowFromPoint($p)
    Write-Output ("{0}: LEFT_CENTER proc={1}" -f $tag, (ProcOf $h))
}

# step 1: activate host
[RS]::SetForegroundWindow($hm) | Out-Null
Start-Sleep -Milliseconds 800
Probe "STEP1_HOST_ACTIVE"

# step 2: activate some other window (ZCode if present)
$zc = Get-Process ZCode -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($zc) {
    [RS]::SetForegroundWindow([IntPtr]$zc.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 800
    Probe "STEP2_SWITCHED_AWAY"
}

# step 3: back to host
[RS]::SetForegroundWindow($hm) | Out-Null
Start-Sleep -Milliseconds 1200
Probe "STEP3_BACK_TO_HOST"
