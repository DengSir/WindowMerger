using System.Windows;

namespace WindowMerger;

/// <summary>布局种类（config.json 的 Layout 字段字符串，大小写不敏感）。</summary>
public enum PaneLayoutKind
{
    LR,     // 左右两格
    LCR,    // 左中右三格
    LTR,    // 左格 + 右列上下两格
    Quad,   // 四宫格（十字分隔）
}

/// <summary>分隔条轴：竖直（左右分界）/ 水平（上下分界）。</summary>
public enum DividerAxis
{
    Vertical,
    Horizontal,
}

/// <summary>
/// 单个布局的静态定义：格子数、中文格名、几何公式、分隔条清单、图标象限槽位。
/// 所有矩形都是<b>内容区相对</b>的 DIP 坐标（内容区 = 窗口减去外框与顶条占位后的窗格区），
/// 宿主把 (cw, ch, r1, r2, dividerW) 喂进来换取实际矩形——本类只算几何，
/// 不做任何 Win32/WPF 布局操作，可在单测/探针中独立验证。
/// r1 = 主比例（左右分界或左宽占比），r2 = 次比例（含义随布局：LCR = 中格占余下宽度的比例；
/// LTR/Quad = 上下分界）。分隔条占地从内容区扣除后，剩余净面积按比例分给格子。
/// </summary>
public sealed class PaneLayoutDef
{
    private PaneLayoutDef(PaneLayoutKind kind, string configName, string[] paneNames, int?[] iconSlots)
    {
        Kind = kind;
        ConfigName = configName;
        PaneNames = paneNames;
        IconSlots = iconSlots;
    }

    public PaneLayoutKind Kind { get; }
    public string ConfigName { get; }
    public string[] PaneNames { get; }
    public int PaneCount => PaneNames.Length;
    /// <summary>比例个数：LR 单比例，其余双比例（宿主持有 _ratio/_ratio2）。</summary>
    public int RatioCount => Kind == PaneLayoutKind.LR ? 1 : 2;
    /// <summary>分隔条个数：LR 一根竖条；LCR 两竖；LTR 竖+右列横；Quad 十字两根
    /// （全高竖 + 全宽横——不是格数-1 的"边到边段"模型，4 格也只有 2 根）。</summary>
    public int DividerCount => Kind == PaneLayoutKind.LR ? 1 : 2;
    /// <summary>竖直分隔条个数：内容区净宽要按它扣减（LCR 两根，其余一根）。</summary>
    public int VDividerCount => Kind == PaneLayoutKind.LCR ? 2 : 1;

    /// <summary>每格对应的 2×2 象限槽位（0=左上 1=右上 2=左下 3=右下），任务栏合成图标用；
    /// 空槽不画。LR 的 [左下,右上] 与旧版双子对角合成逐值一致。</summary>
    public int?[] IconSlots { get; }

    public static readonly PaneLayoutDef LeftRight = new(
        PaneLayoutKind.LR, "LR", new[] { "左", "右" }, new int?[] { 2, 1 });

    public static readonly PaneLayoutDef LeftCenterRight = new(
        PaneLayoutKind.LCR, "LCR", new[] { "左", "中", "右" }, new int?[] { 2, 0, 1 });

    public static readonly PaneLayoutDef LeftTopRightBottom = new(
        PaneLayoutKind.LTR, "LTR", new[] { "左", "右上", "右下" }, new int?[] { 2, 1, 3 });

    public static readonly PaneLayoutDef Quad = new(
        PaneLayoutKind.Quad, "Quad", new[] { "左上", "右上", "左下", "右下" }, new int?[] { 0, 1, 2, 3 });

    public static PaneLayoutDef For(PaneLayoutKind kind) => kind switch
    {
        PaneLayoutKind.LCR => LeftCenterRight,
        PaneLayoutKind.LTR => LeftTopRightBottom,
        PaneLayoutKind.Quad => Quad,
        _ => LeftRight,
    };

    /// <summary>config Layout 字符串 → 布局定义；非法/空返回 null（调用方回退默认 LR）。</summary>
    public static PaneLayoutDef? FromConfig(string? name)
    {
        if (string.IsNullOrWhiteSpace(name)) return null;
        return Enum.TryParse<PaneLayoutKind>(name.Trim(), ignoreCase: true, out var kind) ? For(kind) : null;
    }

    // ---------- 几何 ----------

    /// <summary>格子矩形（内容区相对 DIP，行主序 = PaneNames 顺序）。
    /// LR 公式与旧版 PaneRectDevice 逐值一致（净宽 = cw - dv，左宽 = 净宽 × r1）。</summary>
    public Rect[] PaneRects(double cw, double ch, double r1, double r2, double dv)
        => Kind switch
        {
            PaneLayoutKind.LCR => LcrPanes(cw, ch, r1, r2, dv),
            PaneLayoutKind.LTR => LtrPanes(cw, ch, r1, r2, dv),
            PaneLayoutKind.Quad => QuadPanes(cw, ch, r1, r2, dv),
            _ => LrPanes(cw, ch, r1, dv),
        };

    /// <summary>分隔条矩形（内容区相对 DIP，数组序 = 生成/命中序）。竖条全高；横条按布局
    /// 只跨所属区域（LTR 仅右列、Quad 全宽成十字）。</summary>
    public (DividerAxis Axis, Rect Rect)[] DividerRects(double cw, double ch, double r1, double r2, double dv)
        => Kind switch
        {
            PaneLayoutKind.LCR => LcrDividers(cw, ch, r1, r2, dv),
            PaneLayoutKind.LTR => LtrDividers(cw, ch, r1, r2, dv),
            PaneLayoutKind.Quad => QuadDividers(cw, ch, r1, r2, dv),
            _ => new[] { (DividerAxis.Vertical, new Rect(cw - dv > 0 ? (cw - dv) * r1 : 0, 0, dv, ch)) },
        };

    private static Rect[] LrPanes(double cw, double ch, double r1, double dv)
    {
        double avail = Math.Max(0, cw - dv);
        double lw = avail * r1;
        return new[]
        {
            new Rect(0, 0, lw, ch),
            new Rect(lw + dv, 0, Math.Max(0, cw - lw - dv), ch),
        };
    }

    private static Rect[] LcrPanes(double cw, double ch, double r1, double r2, double dv)
    {
        double avail = Math.Max(0, cw - 2 * dv);
        double lw = avail * r1;
        double rem = avail - lw;
        double cw2 = rem * r2;
        return new[]
        {
            new Rect(0, 0, lw, ch),
            new Rect(lw + dv, 0, cw2, ch),
            new Rect(lw + dv + cw2 + dv, 0, Math.Max(0, rem - cw2), ch),
        };
    }

    private static Rect[] LtrPanes(double cw, double ch, double r1, double r2, double dv)
    {
        double availW = Math.Max(0, cw - dv);
        double availH = Math.Max(0, ch - dv);
        double lw = availW * r1;
        double rw = Math.Max(0, availW - lw);
        double th = availH * r2;
        return new[]
        {
            new Rect(0, 0, lw, ch),
            new Rect(lw + dv, 0, rw, th),
            new Rect(lw + dv, th + dv, rw, Math.Max(0, ch - th - dv)),
        };
    }

    private static Rect[] QuadPanes(double cw, double ch, double r1, double r2, double dv)
    {
        double availW = Math.Max(0, cw - dv);
        double availH = Math.Max(0, ch - dv);
        double lw = availW * r1;
        double rw = Math.Max(0, availW - lw);
        double th = availH * r2;
        double bh = Math.Max(0, availH - th);
        return new[]
        {
            new Rect(0, 0, lw, th),
            new Rect(lw + dv, 0, rw, th),
            new Rect(0, th + dv, lw, bh),
            new Rect(lw + dv, th + dv, rw, bh),
        };
    }

    private static (DividerAxis, Rect)[] LcrDividers(double cw, double ch, double r1, double r2, double dv)
    {
        double avail = Math.Max(0, cw - 2 * dv);
        double lw = avail * r1;
        double cw2 = (avail - lw) * r2;
        return new[]
        {
            (DividerAxis.Vertical, new Rect(lw, 0, dv, ch)),
            (DividerAxis.Vertical, new Rect(lw + dv + cw2, 0, dv, ch)),
        };
    }

    private static (DividerAxis, Rect)[] LtrDividers(double cw, double ch, double r1, double r2, double dv)
    {
        double availW = Math.Max(0, cw - dv);
        double availH = Math.Max(0, ch - dv);
        double lw = availW * r1;
        double rw = Math.Max(0, availW - lw);
        return new[]
        {
            (DividerAxis.Vertical, new Rect(lw, 0, dv, ch)),                    // 全高竖条
            (DividerAxis.Horizontal, new Rect(lw + dv, availH * r2, rw, dv)),   // 仅右列横条
        };
    }

    private static (DividerAxis, Rect)[] QuadDividers(double cw, double ch, double r1, double r2, double dv)
    {
        double availW = Math.Max(0, cw - dv);
        double availH = Math.Max(0, ch - dv);
        return new[]
        {
            (DividerAxis.Vertical, new Rect(availW * r1, 0, dv, ch)),        // 全高竖条
            (DividerAxis.Horizontal, new Rect(0, availH * r2, cw, dv)),      // 全宽横条（十字交叉）
        };
    }

    // ---------- 分隔条拖拽 ----------

    /// <summary>分隔条拖动：光标（内容区 DIP）→ 所控比例的新值（未钳制）。光标钉在分隔条
    /// 中心——与命中测试/矩形公式同一坐标系，替代旧版带 2*borderW 偏移的拖拽公式。</summary>
    public double RatioFromDivider(int divider, Point cursor, double cw, double ch, double r1, double r2, double dv)
        => Kind switch
        {
            // LCR 第二根竖条在"余下区域"内：起点 = 左格净宽 + dv，净长 = 余下净宽
            PaneLayoutKind.LCR when divider == 1 => (cursor.X - (cw - 2 * dv) * r1 - dv - dv / 2)
                                                / Math.Max(1, (cw - 2 * dv) * (1 - r1)),
            // LTR/Quad 的横条与竖条同形：光标分量减半条宽后按净高（净宽）归一
            PaneLayoutKind.LTR when divider == 1 => (cursor.Y - dv / 2) / Math.Max(1, ch - dv),
            PaneLayoutKind.Quad when divider == 1 => (cursor.Y - dv / 2) / Math.Max(1, ch - dv),
            // 主竖条：净宽按竖条数扣减（LR/LTR/Quad 一根、LCR 两根）
            _ => (cursor.X - dv / 2) / Math.Max(1, cw - dv * VDividerCount),
        };

    /// <summary>拖动比例钳制：先按全局 [0.2, 0.8]，再叠加"每格 ≥ minPane DIP"的联合约束
    /// （另一比例固定求解可行域）——防 LCR 中格被挤到百分之几的极小格。</summary>
    public double ClampRatio(int ratioIndex, double raw, double other, double cw, double ch, double dv, double minPane)
    {
        const double lo0 = 0.2, hi0 = 0.8;
        switch (Kind)
        {
            case PaneLayoutKind.LCR:
            {
                double avail = Math.Max(1, cw - 2 * dv);
                if (ratioIndex == 0)
                {
                    // 左 ≥ m → r1 ≥ m/avail；中 = avail*(1-r1)*r2 ≥ m → r1 ≤ 1 - m/(avail*r2)；
                    // 右 = avail*(1-r1)*(1-r2) ≥ m → r1 ≤ 1 - m/(avail*(1-r2))
                    double lo = Math.Max(lo0, minPane / avail);
                    double hi = Math.Min(hi0, Math.Min(
                        1 - minPane / Math.Max(1, avail * other),
                        1 - minPane / Math.Max(1, avail * (1 - other))));
                    return Math.Clamp(raw, Math.Min(lo, hi), Math.Max(lo, hi));
                }
                // 中/右各 ≥ m：r2 ≥ m/((1-r1)*avail)，r2 ≤ 1 - m/((1-r1)*avail)
                double rem = Math.Max(1, avail * (1 - other));
                return Math.Clamp(raw, Math.Max(lo0, minPane / rem), Math.Min(hi0, 1 - minPane / rem));
            }
            case PaneLayoutKind.LTR:
            {
                if (ratioIndex == 0) return WidthClamp(raw, cw, dv, minPane);
                double availH = Math.Max(1, ch - dv);
                return Math.Clamp(raw, Math.Max(lo0, minPane / availH), Math.Min(hi0, 1 - minPane / availH));
            }
            case PaneLayoutKind.Quad:
                return ratioIndex == 0
                    ? WidthClamp(raw, cw, dv, minPane)
                    : HeightClamp(raw, ch, dv, minPane);
            default:
                return WidthClamp(raw, cw, dv, minPane);
        }
    }

    private static double WidthClamp(double raw, double cw, double dv, double minPane)
    {
        double avail = Math.Max(1, cw - dv);
        return Math.Clamp(raw, Math.Max(0.2, minPane / avail), Math.Min(0.8, 1 - minPane / avail));
    }

    private static double HeightClamp(double raw, double ch, double dv, double minPane)
    {
        double avail = Math.Max(1, ch - dv);
        return Math.Clamp(raw, Math.Max(0.2, minPane / avail), Math.Min(0.8, 1 - minPane / avail));
    }
}
