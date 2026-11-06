# ASCII-only: deterministic attach verification — style + rect (no screen probes).
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECTC { public int L, T, R, B; }
public static class CV {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTC r);
}
"@
[CV]::SetProcessDPIAware() | Out-Null

$host_ = Get-Process WindowMerger -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $host_ -or $host_.MainWindowHandle -eq 0) { Write-Output "NO_HOST"; exit 1 }
$hr = New-Object RECTC
[CV]::GetWindowRect([IntPtr]$host_.MainWindowHandle, [ref]$hr) | Out-Null
Write-Output ("HOST ({0},{1})-({2},{3})" -f $hr.L, $hr.T, $hr.R, $hr.B)

$ratio = 0.5
try { $ratio = (Get-Content "$env:APPDATA\WindowMerger\config.json" -Raw | ConvertFrom-Json).Ratio } catch {}
$paneW = [int](($hr.R - $hr.L - 4 - 8) * $ratio)

Get-Process Notepad, mspaint -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    $h = [IntPtr]$_.MainWindowHandle
    $tool = (([CV]::GetWindowLong($h, -20) -band 0x80) -ne 0)
    $r = New-Object RECTC
    [CV]::GetWindowRect($h, [ref]$r) | Out-Null
    Write-Output ("{0} tool={1} rect=({2},{3})-({4},{5})" -f $_.ProcessName, $tool, $r.L, $r.T, $r.R, $r.B)
    if ($_.ProcessName -eq "Notepad") {
        # expected left pane: L=hr.L+2-7, T=hr.T+2+28, R=hr.L+2+paneW+7, B=hr.B-2+7
        $expL = $hr.L + 2 - 7; $expT = $hr.T + 2 + 28; $expR = $hr.L + 2 + $paneW + 7; $expB = $hr.B - 2 + 7
        $dx = [Math]::Abs($r.L - $expL) + [Math]::Abs($r.T - $expT) + [Math]::Abs($r.R - $expR) + [Math]::Abs($r.B - $expB)
        Write-Output ("  LEFT_PANE_DEV={0}" -f $dx)
    }
    if ($_.ProcessName -eq "mspaint") {
        $expL = $hr.L + 2 + $paneW + 8 - 7; $expT = $hr.T + 2 + 28; $expR = $hr.R - 2 + 7; $expB = $hr.B - 2 + 7
        $dx = [Math]::Abs($r.L - $expL) + [Math]::Abs($r.T - $expT) + [Math]::Abs($r.R - $expR) + [Math]::Abs($r.B - $expB)
        Write-Output ("  RIGHT_PANE_DEV={0}" -f $dx)
    }
}
Write-Output ATTACH_CHECK_DONE
