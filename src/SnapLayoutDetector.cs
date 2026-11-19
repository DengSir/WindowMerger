namespace WindowMerger;

/// <summary>接管落位计划：宿主落位矩形（物理 px）+ 布局与双比例覆盖（宿主 ctor 据此
/// 跳过 config 几何、覆写 _layout/_ratio/_ratio2）。命名空间层 public record——
/// StartupOptions.Snap 的属性类型（嵌套在 internal 检测器里会触发 CS0053）。</summary>
public sealed record SnapPlan((double X, double Y, double W, double H) Rect,
    PaneLayoutDef Layout, double Ratio, double Ratio2);

/// <summary>
/// Win11 snap 布局黑盒几何检测。snap 分区/成员没有公开查询 API（微软 Q&A 确认），只能按
/// 几何推断：可见顶层窗口的<b>扩展框架边界（EFB）</b>互相贴合、并集 ≈ 某屏工作区。
/// 必须用 EFB——GetWindowRect 带 ~7px 隐形边，snap 相邻窗在 GetWindowRect 域会互相重叠
/// 约 14px，"无重叠"判据会全军覆没。不区分 shell snap 与手动对齐：用户按热键的意图就是
/// 接管当前排列。多布局接管（2026-11-18）：贴合子集按形状匹配四种布局——2 窗竖分=LR、
/// 3 窗=LCR/LTR（左全高+右列上下）、4 窗=Quad；其余形状（上下两格/镜像 LTR/T 形等）
/// 报 UNSUPPORTED，5+ 窗报 TOO_MANY:n。
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

    /// <summary>一块屏上贴合排布的窗口组：Windows 按<b>布局格序</b>排列（2~4 窗）。
    /// MonitorIndex = EnumDisplayMonitors 顺序。嵌套 internal 类内——public 签名暴露
    /// internal 的 Native.RECT 会 CS0051，跨类型引用须限定 SnapLayoutDetector. 前缀。</summary>
    public sealed record SnapGroup(int MonitorIndex, IntPtr HMonitor, Native.RECT WorkArea,
        List<SnapWindow> Windows, PaneLayoutDef Layout, double Ratio, double Ratio2);

    /// <summary>形状匹配产物（Classify 共用）：布局定义 + pane 序窗口 + 派生比例。</summary>
    private sealed record LayoutMatch(PaneLayoutDef Layout, List<SnapWindow> Ordered,
        double Ratio, double Ratio2);

    /// <summary>检测结果。Group != null = 可接管；ReasonCode 是 ASCII 报因码（detect 子命令 stdout 用，
    /// CI cp1252 控制台安全），Reason 是中文报因（托盘 balloon 用）。</summary>
    public sealed record DetectResult(SnapGroup? Group, string ReasonCode, string Reason);

    /// <summary>检测全部显示器并按"前台窗口所在屏 → 光标所在屏 → 任意"挑一组。
    /// ownedFilter：调用方注入的"已被本进程宿主吸附"判定（App.OwnsAttachedChild）——
    /// 宿主（尤其最大化时）的吸附子窗拼满工作区会被几何判据误识别成 snap 组，
    /// 开新接管宿主去吸它们 = 新旧两只维护定时器互搏（抢窗），必须在候选阶段排除。</summary>
    public static DetectResult DetectAndPick(Func<IntPtr, bool>? ownedFilter = null)
    {
        var monitors = EnumMonitors(); // 顺序与索引 = EnumDisplayMonitors 顺序（测试同款口径）
        var groups = new List<SnapGroup>();
        var unsupported = new List<int>();  // 3/4 窗拼满但形状不在四种布局内（T 形/镜像等，报因）
        var stacked = new List<int>();      // 恰好 2 窗拼满但上下排列（无对应布局，报因）
        var many = new List<(int Index, int Count)>(); // 5+ 窗拼满（超出支持格数）

        var buckets = new Dictionary<IntPtr, List<SnapWindow>>();
        foreach (var w in EnumSnapCandidates(ownedFilter))
        {
            IntPtr mon = Native.MonitorNearestFromWindow(w.Hwnd);
            if (!buckets.TryGetValue(mon, out var list)) buckets[mon] = list = new List<SnapWindow>();
            list.Add(w);
        }

        for (int i = 0; i < monitors.Count; i++)
        {
            var (hMon, wa) = monitors[i];
            var wins = (buckets.TryGetValue(hMon, out var b) ? b : new List<SnapWindow>())
                .Where(w => ZoneEligible(w.Bounds, wa))
                .ToList();
            var (group, isStacked, isUnsupported, manyCount) = Classify(wins, wa, i, hMon);
            if (group is not null) groups.Add(group);
            else if (manyCount > 4) many.Add((i, manyCount)); // 5+ 窗贴满：格数报因优先于形状报因
            else if (isUnsupported) unsupported.Add(i);
            else if (isStacked) stacked.Add(i);
            // 其余（两窗 bbox 拼满但互不贴边 = 中间有缝）：不成布局，跳过
        }

        return Pick(groups, unsupported, stacked, many, monitors);
    }

    /// <summary>
    /// 接管落位计划（托盘进程内直开宿主用）：检测结果组 → SnapPlan（矩形取组工作区，
    /// 布局/双比例 = 形状匹配产物）。宿主 ctor 据此跳过 config 几何、覆写 _layout/_ratio/_ratio2。
    /// </summary>
    public static SnapPlan PlanFromGroup(SnapGroup g)
        => new((g.WorkArea.Left, g.WorkArea.Top,
            (double)g.WorkArea.Width, (double)g.WorkArea.Height),
            g.Layout, g.Ratio, g.Ratio2);

    // ---------- 挑组 ----------

    private static DetectResult Pick(List<SnapGroup> groups, List<int> unsupported, List<int> stacked,
        List<(int Index, int Count)> many, List<(IntPtr HMon, Native.RECT Work)> monitors)
    {
        DetectResult NoLayout() => new(null, "NO_LAYOUT",
            "未发现 snap 布局（需要窗口贴合排满某块屏幕的工作区）");
        DetectResult Stacked(int _) => new(null, "STACKED",
            "上下排列的两窗暂不支持（支持：左右两格/左中右三列/左全高+右列上下/四宫格）");
        DetectResult Unsupported(int _) => new(null, "UNSUPPORTED",
            "该 snap 形状暂不支持（支持：左右两格/左中右三列/左全高+右列上下/四宫格）");
        DetectResult Many(int count) => new(null, $"TOO_MANY:{count}",
            $"布局含 {count} 个窗口（最多支持 4 个）");

        int? preferred = ForegroundMonitorIndex(monitors) ?? CursorMonitorIndex(monitors);
        if (preferred is int pi)
        {
            var g = groups.FirstOrDefault(g => g.MonitorIndex == pi);
            if (g is not null) return new DetectResult(g, "OK", "OK");
            var m = many.FirstOrDefault(x => x.Index == pi);
            if (m.Count > 0) return Many(m.Count);
            if (unsupported.Contains(pi)) return Unsupported(pi);
            if (stacked.Contains(pi)) return Stacked(pi);
            // 本屏没有：退而求其次抓别屏的（多屏用户可预期）
            if (groups.Count > 0) return new DetectResult(groups[0], "OK", "OK");
        }
        if (groups.Count > 0) return new DetectResult(groups[0], "OK", "OK");
        if (many.Count > 0) return Many(many[0].Count);
        if (unsupported.Count > 0) return Unsupported(unsupported[0]);
        if (stacked.Count > 0) return Stacked(stacked[0]);
        return NoLayout();
    }

    private static int? ForegroundMonitorIndex(List<(IntPtr HMon, Native.RECT Work)> monitors)
    {
        IntPtr fg = Native.GetForegroundWindow();
        if (fg == IntPtr.Zero) return null;
        return IndexOfMonitor(monitors, Native.MonitorNearestFromWindow(fg));
    }

    private static int? CursorMonitorIndex(List<(IntPtr HMon, Native.RECT Work)> monitors)
    {
        if (!Native.TryGetCursorPos(out var pt)) return null;
        return IndexOfMonitor(monitors, Native.MonitorNearestFromPoint(pt));
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
    /// 出屏过滤，真实桌面 N≤~10，毫秒级）：子集按形状匹配四种布局（2 窗竖分=LR、3 窗=
    /// LCR/LTR、4 窗=Quad）→ 接管组；2 窗共享横边 = 上下排列（报因 STACKED）；3/4 窗
    /// 拼满但不成形状（T 形/镜像 LTR/异形列）→ 报因 UNSUPPORTED；5+ 窗 → 报因 TOO_MANY:n。
    /// 不做面积降序贪心去重叠——旧法把"互不重叠的窗口集合"当布局成员，盖住 snap 组的
    /// 漂浮大窗（如恢复态全屏的游戏）会把成员全部挤掉 → kept&lt;2 抓不到布局
    /// （2026-11-14 用户实测 4K@150 屏）；子集搜索只要求<b>存在</b>一个贴合子集，
    /// 其余窗口（无论盖不盖住布局）一律无关。多组候选取成员总面积最大者（确定性）。
    /// </summary>
    private static (SnapGroup? Group, bool Stacked, bool Unsupported, int Many) Classify(
        List<SnapWindow> elig, Native.RECT wa, int monitorIndex, IntPtr hMon)
    {
        SnapGroup? best = null;
        long bestArea = -1;
        bool stacked = false;
        bool unsupported = false;
        int many = 0;
        int n = elig.Count;
        if (n < 2 || n > 20) return (null, false, false, 0); // ≥21 窗（病理桌面）放弃枚举，报 NO_LAYOUT

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
            var union = UnionOf(sub);
            if (Math.Abs(union.Left - wa.Left) > TileTolerance || Math.Abs(union.Top - wa.Top) > TileTolerance
                || Math.Abs(union.Right - wa.Right) > TileTolerance
                || Math.Abs(union.Bottom - wa.Bottom) > TileTolerance)
            {
                continue; // 子集并集拼不满工作区
            }
            var match = MatchLayout(sub, union);
            if (match is not null)
            {
                long area = match.Ordered.Sum(w => (long)w.Bounds.Width * w.Bounds.Height);
                if (area > bestArea)
                {
                    bestArea = area;
                    best = new SnapGroup(monitorIndex, hMon, wa,
                        match.Ordered, match.Layout, match.Ratio, match.Ratio2);
                }
                continue;
            }
            switch (sub.Count)
            {
                case 2:
                    if (SharesHorizontalEdge(sub[0].Bounds, sub[1].Bounds)) stacked = true;
                    // 两窗不贴边（中间有缝）→ 什么都不记
                    break;
                case 3:
                case 4:
                    unsupported = true; // 拼满工作区但形状不在支持清单
                    break;
                default:
                    many = Math.Max(many, sub.Count);
                    break;
            }
        }
        return (best, stacked, unsupported, many);
    }

    // ---------- 形状匹配 ----------

    /// <summary>子集形状 → 四种布局之一（返回的窗口已按布局 pane 序排列）。比例以子集并集
    /// 为分母，与 PaneLayout.cs 的归一化公式语义对齐（宿主 6 DIP 分隔条的占位差被
    /// TileTolerance 与全屏最大化吸收）。</summary>
    private static LayoutMatch? MatchLayout(List<SnapWindow> sub, Native.RECT union)
        => sub.Count switch
        {
            2 => TryMatchLr(sub, union),
            3 => TryMatchLcr(sub, union) ?? TryMatchLtr(sub, union),
            4 => TryMatchQuad(sub, union),
            _ => null,
        };

    /// <summary>LR：两窗共享竖边，比例 = 左窗宽占比。</summary>
    private static LayoutMatch? TryMatchLr(List<SnapWindow> sub, Native.RECT union)
    {
        var (a, z) = sub[0].Bounds.Left <= sub[1].Bounds.Left ? (sub[0], sub[1]) : (sub[1], sub[0]);
        if (!SharesVerticalEdge(a.Bounds, z.Bounds)) return null;
        double ratio = union.Width > 0 ? (double)a.Bounds.Width / union.Width : 0.5;
        return new LayoutMatch(PaneLayoutDef.LeftRight, new List<SnapWindow> { a, z }, ratio, 0.5);
    }

    /// <summary>LCR：三竖列全高、相邻共享竖边；r1 = 左宽占比，r2 = 中格占"余下宽度"比例
    /// （LcrPanes 的 avail/rem 语义）。</summary>
    private static LayoutMatch? TryMatchLcr(List<SnapWindow> sub, Native.RECT union)
    {
        var cols = sub.OrderBy(w => w.Bounds.Left).ToList();
        if (cols.Any(w => !FullHeight(w.Bounds, union))) return null;
        if (!SharesVerticalEdge(cols[0].Bounds, cols[1].Bounds)
            || !SharesVerticalEdge(cols[1].Bounds, cols[2].Bounds)) return null;
        double r1 = union.Width > 0 ? (double)cols[0].Bounds.Width / union.Width : 0.5;
        int rem = union.Width - cols[0].Bounds.Width;
        double r2 = rem > 0 ? (double)cols[1].Bounds.Width / rem : 0.5;
        return new LayoutMatch(PaneLayoutDef.LeftCenterRight, cols, r1, r2);
    }

    /// <summary>LTR：恰一扇全高窗且必须最左（全高窗在最右 = 镜像、无全高窗 = 上大下二
    /// T 形，均不支持），另两扇在右列上下贴边；r1 = 左宽占比，r2 = 右上占右列高比例。</summary>
    private static LayoutMatch? TryMatchLtr(List<SnapWindow> sub, Native.RECT union)
    {
        int fullIdx = -1;
        for (int i = 0; i < sub.Count; i++)
        {
            if (!FullHeight(sub[i].Bounds, union)) continue;
            if (fullIdx >= 0) return null; // 两扇全高：三竖列（LCR 已试过）或异形
            fullIdx = i;
        }
        if (fullIdx < 0) return null;
        var left = sub[fullIdx];
        var others = sub.Where((_, i) => i != fullIdx).OrderBy(w => w.Bounds.Top).ToList();
        var (rt, rb) = (others[0], others[1]);
        // 右列两扇都要从全高窗右缘起步（最右全高 = 镜像 → 拒）
        if (Math.Abs(rt.Bounds.Left - left.Bounds.Right) > TileTolerance
            || Math.Abs(rb.Bounds.Left - left.Bounds.Right) > TileTolerance) return null;
        if (Math.Abs(rt.Bounds.Top - union.Top) > TileTolerance
            || Math.Abs(rb.Bounds.Bottom - union.Bottom) > TileTolerance) return null;
        if (!SharesHorizontalEdge(rt.Bounds, rb.Bounds)) return null;
        double r1 = union.Width > 0 ? (double)left.Bounds.Width / union.Width : 0.5;
        int colH = rt.Bounds.Height + rb.Bounds.Height;
        double r2 = colH > 0 ? (double)rt.Bounds.Height / colH : 0.5;
        return new LayoutMatch(PaneLayoutDef.LeftTopRightBottom, new List<SnapWindow> { left, rt, rb }, r1, r2);
    }

    /// <summary>Quad：2×2 四象限——上排贴顶、下排贴底，竖界 X 对两行一致、横界 Y 对两列
    /// 一致；r1/r2 = 十字分界的归一化位置。</summary>
    private static LayoutMatch? TryMatchQuad(List<SnapWindow> sub, Native.RECT union)
    {
        var top = sub.Where(w => Math.Abs(w.Bounds.Top - union.Top) <= TileTolerance)
            .OrderBy(w => w.Bounds.Left).ToList();
        var bottom = sub.Where(w => Math.Abs(w.Bounds.Top - union.Top) > TileTolerance)
            .OrderBy(w => w.Bounds.Left).ToList();
        if (top.Count != 2 || bottom.Count != 2) return null;
        if (bottom.Any(w => Math.Abs(w.Bounds.Bottom - union.Bottom) > TileTolerance)) return null;
        // 行内左右贴边，两行的竖界一致
        if (Math.Abs(top[0].Bounds.Right - top[1].Bounds.Left) > TileTolerance
            || Math.Abs(bottom[0].Bounds.Right - bottom[1].Bounds.Left) > TileTolerance) return null;
        int xTop = (top[0].Bounds.Right + top[1].Bounds.Left) / 2;
        int xBottom = (bottom[0].Bounds.Right + bottom[1].Bounds.Left) / 2;
        if (Math.Abs(xTop - xBottom) > TileTolerance) return null;
        // 列内上下贴边，两列的横界一致
        if (Math.Abs(top[0].Bounds.Bottom - bottom[0].Bounds.Top) > TileTolerance
            || Math.Abs(top[1].Bounds.Bottom - bottom[1].Bounds.Top) > TileTolerance) return null;
        int yLeft = (top[0].Bounds.Bottom + bottom[0].Bounds.Top) / 2;
        int yRight = (top[1].Bounds.Bottom + bottom[1].Bounds.Top) / 2;
        if (Math.Abs(yLeft - yRight) > TileTolerance) return null;
        double r1 = union.Width > 0 ? (double)(xTop - union.Left) / union.Width : 0.5;
        double r2 = union.Height > 0 ? (double)(yLeft - union.Top) / union.Height : 0.5;
        var ordered = new List<SnapWindow> { top[0], top[1], bottom[0], bottom[1] }; // 左上/右上/左下/右下
        return new LayoutMatch(PaneLayoutDef.Quad, ordered, r1, r2);
    }

    /// <summary>窗占并集整高（上下缘齐平，容差内）。</summary>
    private static bool FullHeight(Native.RECT r, Native.RECT union)
        => Math.Abs(r.Top - union.Top) <= TileTolerance
        && Math.Abs(r.Bottom - union.Bottom) <= TileTolerance;

    private static Native.RECT UnionOf(List<SnapWindow> wins)
        => new()
        {
            Left = wins.Min(w => w.Bounds.Left),
            Top = wins.Min(w => w.Bounds.Top),
            Right = wins.Max(w => w.Bounds.Right),
            Bottom = wins.Max(w => w.Bounds.Bottom),
        };

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
            if (Native.TryGetMonitorInfo(hMon, out var mi)) list.Add((hMon, mi.rcWork));
            return true;
        }, IntPtr.Zero);
        return list;
    }

    /// <summary>候选窗枚举：可见、未 cloak、非最小化/最大化、非工具窗、无 owner、非 shell 杂窗、
    /// 非自己（含其他 WindowMerger 实例——口径与 WindowLocator.GetCandidates 一致）、
    /// 非本进程宿主的吸附子窗（ownedFilter，外部进程窗口须按占有关系排除）。</summary>
    private static List<SnapWindow> EnumSnapCandidates(Func<IntPtr, bool>? ownedFilter = null)
    {
        uint selfPid = (uint)Environment.ProcessId;
        var found = new List<SnapWindow>();
        Native.EnumWindows((h, _) =>
        {
            if (!Native.IsWindowVisible(h) || Native.IsCloaked(h) || Native.IsIconic(h) || Native.IsZoomed(h)) return true;
            if (Native.HasExStyle(h, Native.WindowExStyles.ToolWindow)) return true;
            if (Native.GetRelatedWindow(h, Native.GetWindowRelation.Owner) != IntPtr.Zero) return true;
            if (ownedFilter?.Invoke(h) == true) return true; // 已被本进程宿主吸附：不是外部 snap 布局
            if (WindowLocator.ExcludedClasses.Contains(Native.GetClassNameOf(h))) return true;
            uint pid = Native.GetPid(h);
            if (pid == selfPid || WindowLocator.IsOtherSelf(pid, selfPid)) return true;
            if (Native.GetTitle(h).Length == 0) return true;
            if (EfbOf(h) is not { } efb) return true;
            found.Add(new SnapWindow(h, efb));
            return true;
        }, IntPtr.Zero);
        return found;
    }

    private static Native.RECT? EfbOf(IntPtr hwnd)
        => Native.TryGetExtendedFrameBounds(hwnd, out var rect) ? rect : null;
}
