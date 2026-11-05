# ASCII-only: scan all top-level WS_EX_TOOLWINDOW windows (the orphan signature),
# or rescue orphans of a given process: strip the style, show, and pull back
# on-screen windows stuck at -32000.
param(
    [switch]$Rescue,
    [string]$ProcName = ""
)
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct RECTO { public int L, T, R, B; }
public static class OR {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr GetTopWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern int SetWindowLong(IntPtr h, int i, int v);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECTO r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int m);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
}
"@
[OR]::SetProcessDPIAware() | Out-Null

$screenW = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea.Width
$screenH = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea.Height
Add-Type -AssemblyName System.Windows.Forms

$cur = [OR]::GetTopWindow([IntPtr]::Zero)
$cascade = 0
$found = 0
for ($i = 0; $i -lt 600 -and $cur -ne [IntPtr]::Zero; $i++) {
    $ex = [OR]::GetWindowLong($cur, -20)
    if (($ex -band 0x80) -ne 0) {
        $procId = 0
        [OR]::GetWindowThreadProcessId($cur, [ref]$procId) | Out-Null
        $pn = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { "?" }
        $match = ($ProcName -eq "") -or ($pn -ieq $ProcName)
        if ($match) {
            $found++
            $sb = New-Object System.Text.StringBuilder 48
            [OR]::GetClassName($cur, $sb, 48) | Out-Null
            $tb = New-Object System.Text.StringBuilder 64
            [OR]::GetWindowText($cur, $tb, 64) | Out-Null
            $r = New-Object RECTO
            [OR]::GetWindowRect($cur, [ref]$r) | Out-Null
            $vis = [OR]::IsWindowVisible($cur)
            $off = ($r.L -le -30000 -or $r.T -le -30000)
            Write-Output ("hwnd=0x{0:X} proc={1} pid={2} vis={3} offscreen={4} rect=({5},{6})-({7},{8}) class={9} title=[{10}]" -f $cur.ToInt64(), $pn, $procId, $vis, $off, $r.L, $r.T, $r.R, $r.B, $sb.ToString(), $tb.ToString())
            if ($Rescue) {
                if (-not $vis) {
                    Write-Output "  SKIP rescue: hidden helper window (never ours)"
                } else {
                    $newEx = $ex -band (-bnot 0x80)
                    [OR]::SetWindowLong($cur, -20, $newEx) | Out-Null
                    [OR]::ShowWindow($cur, 8) | Out-Null    # SW_SHOWNA
                    if ($off) {
                        $x = 60 + ($cascade % 5) * 40
                        $y = 60 + ($cascade % 5) * 40
                        $cascade++
                        $w = [Math]::Min(1200, $screenW - 120)
                        $h = [Math]::Min(800, $screenH - 120)
                        [OR]::SetWindowPos($cur, [IntPtr]::Zero, $x, $y, $w, $h, 0x0004) | Out-Null  # SWP_NOZORDER
                        Write-Output ("  RESCUED: style stripped, shown, moved to ({0},{1}) {2}x{3}" -f $x, $y, $w, $h)
                    } else {
                        Write-Output "  RESCUED: style stripped, shown"
                    }
                }
            }
        }
    }
    $cur = [OR]::GetWindow($cur, 2)
}
if ($found -eq 0) { Write-Output "NO_TOOLWINDOW_WINDOWS" }
Write-Output ORPHAN_SCAN_DONE
