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
            // 排除"另一个自己"：其他 WindowMerger 实例的宿主窗口不进候选
            if (procNames.TryGetValue(pid, out var pn) && IsSelfProcessName(pn)) return true;

            string pname = procNames.TryGetValue(pid, out var n) ? n : "?";
            results.Add(new WindowCandidate(h, title, Native.GetClassNameOf(h), pname, pid));
            return true;
        }, IntPtr.Zero);

        results.Sort((a, b) => string.Compare(a.ProcessName, b.ProcessName, StringComparison.OrdinalIgnoreCase));
        return results;
    }

    /// <summary>"自己"的进程名前缀：含发布重命名变体（WindowMerger-&lt;版本&gt;-win-x64.exe）。</summary>
    private const string SelfProcessPrefix = "WindowMerger";

    private static bool IsSelfProcessName(string processName)
        => processName.StartsWith(SelfProcessPrefix, StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// 窗口是否属于"另一个自己"——其他 WindowMerger 实例。它的宿主窗口不能被抓进格子、
    /// 也不进选择器候选（其对话框有 Owner，本就被排除）。
    /// </summary>
    public static bool IsOtherSelf(uint pid, uint selfPid)
    {
        if (pid == selfPid || pid == 0) return false;
        try
        {
            return IsSelfProcessName(Process.GetProcessById((int)pid).ProcessName);
        }
        catch (ArgumentException)
        {
            return false; // 进程已退出（快照间隙），窗口随后也会消失
        }
    }
}
