using System.Runtime.InteropServices;

namespace WindowMerger;

/// <summary>
/// Win11 snap 布局黑盒几何检测。snap 分区/成员没有公开查询 API（微软 Q&A 确认），只能按
/// 几何推断：可见顶层窗口的<b>扩展框架边界（EFB）</b>互相贴合、并集 ≈ 某屏工作区。
/// 必须用 EFB——GetWindowRect 带 ~7px 隐形边，snap 相邻窗在 GetWindowRect 域会互相重叠
/// 约 14px，"无重叠"判据会全军覆没。不区分 shell snap 与手动对齐：用户按热键的意图就是
/// 接管当前排列。v1 只接管"恰好 2 窗的左右对分"（Win11 两区模板 对半/2:1 都在此口径内）。
/// internal：公开签名会暴露 internal 的 Native.RECT（CS0051）；调用方 App/TrayController 同程序集。
/// </summary>
internal static class SnapLayoutDetector
{
    /// <summary>贴合容差（物理 px）：snap 分区精确贴合，容差只吸收 DPI 取整误差。</summary>
    private const int TileTolerance = 8;

    /// <summary>单窗面积下限（占工作区比例）：排除针尖小杂窗参与拼图（最小 snap 分区 ≈ 1/4 屏）。</summary>
    private const double MinZoneFraction = 0.05;

    /// <summary>候选窗口：Hwnd + 可见边界（EFB，物理 px）。</summary>
    public sealed record SnapWindow(IntPtr Hwnd, Native.RECT Bounds);

    /// <summary>一块屏上贴合排布的窗口组（v1 = 恰好 2 窗、左右对分）。MonitorIndex = EnumDisplayMonitors 顺序。</summary>
    public sealed record SnapGroup(int MonitorIndex, IntPtr HMonitor, Native.RECT WorkArea,
        List<SnapWindow> Windows, double LeftFraction);

    /// <summary>检测结果。Group != null = 可接管；ReasonCode 是 ASCII 报因码（--detect-snap stdout 用，
    /// CI cp1252 控制台安全），Reason 是中文报因（托盘 balloon 用）。</summary>
    public sealed record DetectResult(SnapGroup? Group, string ReasonCode, string Reason);

    /// <summary>检测全部显示器并按"前台窗口所在屏 → 光标所在屏 → 任意"挑一组。</summary>
    public static DetectResult DetectAndPick()
    {
        var monitors = EnumMonitors(); // 顺序与索引 = EnumDisplayMonitors 顺序（测试同款口径）
        var pairs = new List<SnapGroup>();
        var stacked = new List<int>();      // 恰好 2 窗拼满但上下排列（v1 不支持，报因）
        var many = new List<(int Index, int Count)>(); // 3+ 窗拼满（多格布局是 v2）

        var buckets = new Dictionary<IntPtr, List<SnapWindow>>();
        foreach (var w in EnumSnapCandidates())
        {
            IntPtr mon = Native.MonitorFromWindow(w.Hwnd, Native.MONITOR_DEFAULTTONEAREST);
            if (!buckets.TryGetValue(mon, out var list)) buckets[mon] = list = new List<SnapWindow>();
            list.Add(w);
        }

        for (int i = 0; i < monitors.Count; i++)
        {
            var (hMon, wa) = monitors[i];
            var wins = (buckets.TryGetValue(hMon, out var b) ? b : new List<SnapWindow>())
                .Where(w => ZoneEligible(w.Bounds, wa))
                .ToList();
            var (pair, isStacked, manyCount) = Classify(wins, wa, i, hMon);
            if (pair is not null) pairs.Add(pair);
            else if (manyCount >= 3) many.Add((i, manyCount));
            else if (isStacked) stacked.Add(i);
            // 其余（两窗 bbox 拼满但互不贴边 = 中间有缝）：不成布局，跳过
        }

        return Pick(pairs, stacked, many, monitors);
    }

    /// <summary>
    /// 接管落位推导（宿主实例自己用）：两窗口 EFB 并集（物理 px）+ 左窗宽占比。
    /// 任一句柄拿不到 EFB 返回 null（宿主走默认居中落位，吸附报因走状态栏）。
    /// </summary>
    public static ((double X, double Y, double W, double H) Rect, double Ratio)? SnapRectFor(IntPtr a, IntPtr b)
    {
        var ra = EfbOf(a);
        var rb = EfbOf(b);
        if (ra is not { } r1 || rb is not { } r2) return null;
        if (r1.Left > r2.Left) (r1, r2) = (r2, r1);
        int l = Math.Min(r1.Left, r2.Left);
        int t = Math.Min(r1.Top, r2.Top);
        int r = Math.Max(r1.Right, r2.Right);
        int bt = Math.Max(r1.Bottom, r2.Bottom);
        if (r <= l || bt <= t) return null;
        double ratio = r - l > 0 ? (double)(r1.Right - r1.Left) / (r - l) : 0.5;
        return ((l, t, (double)r - l, (double)bt - t), ratio);
    }

    // ---------- 挑组 ----------

    private static DetectResult Pick(List<SnapGroup> pairs, List<int> stacked,
        List<(int Index, int Count)> many, List<(IntPtr HMon, Native.RECT Work)> monitors)
    {
        DetectResult NoLayout() => new(null, "NO_LAYOUT",
            "未发现 snap 布局（需要两个窗口贴合排满某块屏幕的工作区）");
        DetectResult Stacked(int _) => new(null, "STACKED",
            "上下排列的窗口暂不支持（当前版本仅支持左右布局）");
        DetectResult Many(int count) => new(null, $"TOO_MANY:{count}",
            $"布局含 {count} 个窗口（当前版本仅支持 2 个）");

        int? preferred = ForegroundMonitorIndex(monitors) ?? CursorMonitorIndex(monitors);
        if (preferred is int pi)
        {
            var g = pairs.FirstOrDefault(g => g.MonitorIndex == pi);
            if (g is not null) return new DetectResult(g, "OK", "OK");
            if (stacked.Contains(pi)) return Stacked(pi);
            var m = many.FirstOrDefault(x => x.Index == pi);
            if (m.Count > 0) return Many(m.Count);
            // 本屏没有：退而求其次抓别屏的（多屏用户可预期）
            if (pairs.Count > 0) return new DetectResult(pairs[0], "OK", "OK");
        }
        if (pairs.Count > 0) return new DetectResult(pairs[0], "OK", "OK");
        if (stacked.Count > 0) return Stacked(stacked[0]);
        if (many.Count > 0) return Many(many[0].Count);
        return NoLayout();
    }

    private static int? ForegroundMonitorIndex(List<(IntPtr HMon, Native.RECT Work)> monitors)
    {
        IntPtr fg = Native.GetForegroundWindow();
        if (fg == IntPtr.Zero) return null;
        return IndexOfMonitor(monitors, Native.MonitorFromWindow(fg, Native.MONITOR_DEFAULTTONEAREST));
    }

    private static int? CursorMonitorIndex(List<(IntPtr HMon, Native.RECT Work)> monitors)
    {
        if (!Native.GetCursorPos(out var pt)) return null;
        return IndexOfMonitor(monitors, Native.MonitorFromPoint(pt, Native.MONITOR_DEFAULTTONEAREST));
    }

    private static int? IndexOfMonitor(List<(IntPtr HMon, Native.RECT Work)> monitors, IntPtr hMon)
    {
        for (int i = 0; i < monitors.Count; i++)
            if (monitors[i].HMon == hMon) return i;
        return null;
    }

    // ---------- 几何判据 ----------

    /// <summary>单窗参与拼图的资格：完整落在工作区内（容差）且面积 ≥ 下限。</summary>
    private static bool ZoneEligible(Native.RECT r, Native.RECT wa)
    {
        if (r.Left < wa.Left - TileTolerance || r.Top < wa.Top - TileTolerance
            || r.Right > wa.Right + TileTolerance || r.Bottom > wa.Bottom + TileTolerance)
        {
            return false;
        }
        long zone = (long)r.Width * r.Height;
        long work = (long)(wa.Right - wa.Left) * (wa.Bottom - wa.Top);
        return work > 0 && zone >= work * MinZoneFraction;
    }

    /// <summary>
    /// 在合格窗集合里搜索"恰好拼满工作区"的贴合子集（2^N 枚举；合格窗已过面积 ≥5% 与
    /// 出屏过滤，真实桌面 N≤~10，毫秒级）：双窗子集共享竖边 = 左右对分（接管目标），
    /// 共享横边 = 上下排列（报因 STACKED），三窗以上 = 多格布局（报因 TOO_MANY:n）。
    /// 不做面积降序贪心去重叠——旧法把"互不重叠的窗口集合"当布局成员，盖住 snap 组的
    /// 漂浮大窗（如恢复态全屏的游戏）会把成员全部挤掉 → kept&lt;2 抓不到布局
    /// （2026-11-14 用户实测 4K@150 屏）；子集搜索只要求<b>存在</b>一个贴合子集，
    /// 其余窗口（无论盖不盖住布局）一律无关。多对候选取成员总面积最大者（确定性）。
    /// </summary>
    private static (SnapGroup? Pair, bool Stacked, int Many) Classify(
        List<SnapWindow> elig, Native.RECT wa, int monitorIndex, IntPtr hMon)
    {
        SnapGroup? best = null;
        long bestArea = -1;
        bool stacked = false;
        int many = 0;
        int n = elig.Count;
        if (n < 2 || n > 20) return (null, false, 0); // ≥21 窗（病理桌面）放弃枚举，报 NO_LAYOUT

        var sub = new List<SnapWindow>(n);
        for (int mask = 3; mask < (1 << n); mask++)
        {
            int cnt = System.Numerics.BitOperations.PopCount((uint)mask);
            if (cnt < 2) continue;
            sub.Clear();
            bool disjoint = true;
            for (int j = 0; j < n && disjoint; j++)
            {
                if ((mask & (1 << j)) == 0) continue;
                foreach (var s in sub)
                    if (Overlaps(s.Bounds, elig[j].Bounds)) { disjoint = false; break; }
                if (disjoint) sub.Add(elig[j]);
            }
            if (!disjoint) continue;
            int l = sub.Min(w => w.Bounds.Left), t = sub.Min(w => w.Bounds.Top);
            int r = sub.Max(w => w.Bounds.Right), b = sub.Max(w => w.Bounds.Bottom);
            if (Math.Abs(l - wa.Left) > TileTolerance || Math.Abs(t - wa.Top) > TileTolerance
                || Math.Abs(r - wa.Right) > TileTolerance || Math.Abs(b - wa.Bottom) > TileTolerance)
            {
                continue; // 子集并集拼不满工作区
            }
            if (cnt == 2)
            {
                var first = sub[0];
                var second = sub[1];
                if (SharesVerticalEdge(first.Bounds, second.Bounds))
                {
                    var (a, z) = first.Bounds.Left <= second.Bounds.Left
                        ? (first, second) : (second, first);
                    int unionW = Math.Max(a.Bounds.Right, z.Bounds.Right)
                               - Math.Min(a.Bounds.Left, z.Bounds.Left);
                    double fraction = unionW > 0 ? (double)a.Bounds.Width / unionW : 0.5;
                    long area = (long)a.Bounds.Width * a.Bounds.Height
                              + (long)z.Bounds.Width * z.Bounds.Height;
                    if (area > bestArea)
                    {
                        bestArea = area;
                        best = new SnapGroup(monitorIndex, hMon, wa,
                            new List<SnapWindow> { a, z }, fraction);
                    }
                }
                else if (SharesHorizontalEdge(first.Bounds, second.Bounds))
                {
                    stacked = true;
                }
            }
            else if (cnt > many)
            {
                many = cnt;
            }
        }
        return (best, stacked, many);
    }

    private static bool Overlaps(Native.RECT a, Native.RECT b)
        => Math.Min(a.Right, b.Right) - Math.Max(a.Left, b.Left) > TileTolerance
        && Math.Min(a.Bottom, b.Bottom) - Math.Max(a.Top, b.Top) > TileTolerance;

    /// <summary>左右对分：两窗共享一条竖直边（矩形二分矩形必沿一条整线，此判据排除上下排列）。</summary>
    private static bool SharesVerticalEdge(Native.RECT a, Native.RECT b)
        => Math.Abs(a.Right - b.Left) <= TileTolerance || Math.Abs(b.Right - a.Left) <= TileTolerance;

    /// <summary>上下排列：两窗共享一条水平边。共享边判据缺一不可——并集判据只看
    /// 并集外接矩形，两窗中间留缝时 bbox 仍等于工作区，会被它漏过（自测推演实锤）。</summary>
    private static bool SharesHorizontalEdge(Native.RECT a, Native.RECT b)
        => Math.Abs(a.Bottom - b.Top) <= TileTolerance || Math.Abs(b.Bottom - a.Top) <= TileTolerance;

    // ---------- 枚举 ----------

    private static List<(IntPtr HMon, Native.RECT Work)> EnumMonitors()
    {
        var list = new List<(IntPtr, Native.RECT)>();
        Native.EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero, (hMon, _, ref _, _) =>
        {
            var mi = new Native.MONITORINFO { cbSize = Marshal.SizeOf<Native.MONITORINFO>() };
            if (Native.GetMonitorInfo(hMon, ref mi)) list.Add((hMon, mi.rcWork));
            return true;
        }, IntPtr.Zero);
        return list;
    }

    /// <summary>候选窗枚举：可见、未 cloak、非最小化/最大化、非工具窗、无 owner、非 shell 杂窗、
    /// 非自己（含其他 WindowMerger 实例——口径与 WindowLocator.GetCandidates 一致）。</summary>
    private static List<SnapWindow> EnumSnapCandidates()
    {
        uint selfPid = (uint)Environment.ProcessId;
        var found = new List<SnapWindow>();
        Native.EnumWindows((h, _) =>
        {
            if (!Native.IsWindowVisible(h) || Native.IsCloaked(h) || Native.IsIconic(h) || Native.IsZoomed(h)) return true;
            if ((Native.GetWindowLong(h, Native.GWL_EXSTYLE) & Native.WS_EX_TOOLWINDOW) != 0) return true;
            if (Native.GetWindow(h, Native.GW_OWNER) != IntPtr.Zero) return true;
            if (WindowLocator.ExcludedClasses.Contains(Native.GetClassNameOf(h))) return true;
            Native.GetWindowThreadProcessId(h, out uint pid);
            if (pid == selfPid || WindowLocator.IsOtherSelf(pid, selfPid)) return true;
            if (Native.GetTitle(h).Length == 0) return true;
            if (EfbOf(h) is not { } efb) return true;
            found.Add(new SnapWindow(h, efb));
            return true;
        }, IntPtr.Zero);
        return found;
    }

    private static Native.RECT? EfbOf(IntPtr hwnd)
        => Native.DwmGetWindowAttributeRect(hwnd, Native.DWMWA_EXTENDED_FRAME_BOUNDS,
               out var rect, Marshal.SizeOf<Native.RECT>()) == 0 ? rect : null;
}
