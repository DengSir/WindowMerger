using System.Diagnostics;

namespace WindowMerger;

public sealed record WindowCandidate(IntPtr Hwnd, string Title, string ClassName, string ProcessName, uint Pid);

public static class WindowLocator
{
    private static readonly HashSet<string> ExcludedClasses = new(StringComparer.OrdinalIgnoreCase)
    {
        "Shell_TrayWnd",
        "Shell_SecondaryTrayWnd",
        "Progman",
        "WorkerW",
        "Windows.UI.Core.CoreWindow",
        "XamlExplorerHostIslandWindow",
    };

    public static List<WindowCandidate> GetCandidates(IntPtr excludeHwnd)
    {
        uint selfPid = (uint)Environment.ProcessId;

        var procNames = new Dictionary<uint, string>();
        foreach (var p in Process.GetProcesses())
        {
            try
            {
                procNames[(uint)p.Id] = p.ProcessName;
            }
            catch
            {
                // 单个进程查询失败（可能刚好退出）不应中断枚举
            }
            finally
            {
                p.Dispose();
            }
        }

        var results = new List<WindowCandidate>();
        Native.EnumWindows((h, _) =>
        {
            if (h == excludeHwnd) return true;
            if (!Native.IsWindowVisible(h) || Native.IsCloaked(h)) return true;

            string title = Native.GetTitle(h);
            if (title.Length == 0) return true;
            if ((Native.GetWindowLong(h, Native.GWL_EXSTYLE) & Native.WS_EX_TOOLWINDOW) != 0) return true;
            if (Native.GetWindow(h, Native.GW_OWNER) != IntPtr.Zero) return true;
            if (ExcludedClasses.Contains(Native.GetClassNameOf(h))) return true;

            uint pid = Native.GetPid(h);
            if (pid == selfPid) return true;

            string pname = procNames.TryGetValue(pid, out var n) ? n : "?";
            results.Add(new WindowCandidate(h, title, Native.GetClassNameOf(h), pname, pid));
            return true;
        }, IntPtr.Zero);

        results.Sort((a, b) => string.Compare(a.ProcessName, b.ProcessName, StringComparison.OrdinalIgnoreCase));
        return results;
    }
}
