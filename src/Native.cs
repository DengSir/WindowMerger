using System.Runtime.InteropServices;
using System.Text;

namespace WindowMerger;

/// <summary>
/// Win32 导入唯一入口，两层结构：
/// 公开层 = C# 风格封装——语义化方法 + 枚举 + Try* 读取器，旗标组合、cbSize/length
///   仪式、所有权语义全部内藏在封装里，调用方不碰魔法数字；
/// 私有层 = 原始 P/Invoke（签名保持与原生一致），文件外禁止直调。
/// 三条铁律（违反必炸，全部实测）：
/// ① LibraryImport 不会自动补 W 后缀——自定义方法名必须显式 EntryPoint 指向真实导出名；
/// ② StringBuilder/字符串出入参必须走经典 DllImport + CharSet.Unicode（漏写按 ANSI
///    反序列化，ToString(0, size) 越界崩宿主）；③ propsys 的 SHGetPropertyStoreForWindow
/// 走 ordinal #4（shell32 同名导出在 Win11 Insider 26300 是坏 stub）。
/// </summary>
internal static partial class Native
{
    // ---------- 委托（回调引用须由调用方字段保活，防 GC） ----------

    public delegate void WinEventProc(IntPtr hWinEventHook, uint @event, IntPtr hwnd, int idObject, int idChild, uint idEventThread, uint dwmsEventTime);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    public delegate bool MonitorEnumProc(IntPtr hMonitor, IntPtr hdc, ref RECT rect, IntPtr data);

    // ---------- 结构体（公开：RECT/POINT/MONITORINFO 流入公开签名与私有布局结构） ----------

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int Left, Top, Right, Bottom;

        public readonly int Width => Right - Left;
        public readonly int Height => Bottom - Top;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT
    {
        public int X, Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MONITORINFO
    {
        public int cbSize;
        public RECT rcMonitor;
        public RECT rcWork;
        public int dwFlags;
    }

    // ---------- 枚举（原生旗标/常量的 C# 化） ----------

    /// <summary>SetWindowPos 的 hWndInsertAfter 预设位（语义 = "放到目标窗口下方"）。</summary>
    public enum ZOrderPosition
    {
        Topmost = -1,
        NotTopmost = -2,
        Top = 0,
    }

    /// <summary>GetWindow 的关系查询。</summary>
    public enum GetWindowRelation
    {
        HwndNext = 2, // GW_HWNDNEXT：z 序中的下一个（下方）窗口
        Owner = 4,    // GW_OWNER：owner 窗口
    }

    /// <summary>扩展窗口样式位（GWL_EXSTYLE 域）。</summary>
    [Flags]
    public enum WindowExStyles
    {
        Transparent = 0x00000020, // WS_EX_TRANSPARENT：点击穿透层
        ToolWindow = 0x00000080,  // WS_EX_TOOLWINDOW：工具窗
    }

    /// <summary>窗口图标种类（WM_GETICON / GetClassLong 双通道共用）。</summary>
    public enum IconKind
    {
        Big = 1,    // ICON_BIG / GCLP_HICON
        Small2 = 2, // ICON_SMALL2 / GCLP_HICONSM（小图标变体）
    }

    /// <summary>全局热键修饰键。</summary>
    [Flags]
    public enum HotkeyModifiers
    {
        Alt = 0x0001,
        Control = 0x0002,
        Shift = 0x0004,
        Win = 0x0008,
    }

    /// <summary>系统级窗口事件（SetWinEventHook 的 eventMin/eventMax）。</summary>
    public enum SystemEvent : uint
    {
        Foreground = 0x0003,  // EVENT_SYSTEM_FOREGROUND
        MoveSize = 0x000A,    // EVENT_SYSTEM_MOVESIZE
        MoveSizeEnd = 0x000B, // EVENT_SYSTEM_MOVESIZEEND
    }

    /// <summary>WinEvent 回调里 idObject 的窗口对象值。</summary>
    public const int OBJID_WINDOW = 0;

    // ---------- 谓词与简单动作（无旗标/缓冲区仪式，原样公开） ----------

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool IsWindow(IntPtr hWnd);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool IsWindowVisible(IntPtr hWnd);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool IsIconic(IntPtr hWnd);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool IsZoomed(IntPtr hWnd);

    [LibraryImport("user32.dll")]
    public static partial IntPtr GetForegroundWindow();

    /// <summary>把前台转交给指定窗口。调用方须持有前台（否则被前台锁静默拒绝），
    /// 返回 false = 被拒（前台锁/UIPI），不致命。</summary>
    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool SetForegroundWindow(IntPtr hWnd);

    /// <summary>把自己持有的前台权转交给另一进程（单实例唤起：第二实例刚被用户启动、
    /// 持前台权，转交给主实例后它开的新窗才能可靠置前，否则只闪任务栏）。无 A/W 变体。</summary>
    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool AllowSetForegroundWindow(uint dwProcessId);

    /// <summary>异步投递窗口消息（单实例唤起 WM_OPEN_HOST）。真实导出有 W 后缀，必须显式
    /// EntryPoint——源生成器不会自动补（GetMonitorInfoW 等三崩之坑）。</summary>
    [LibraryImport("user32.dll", EntryPoint = "PostMessageW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    public static bool RegisterHotKey(IntPtr hWnd, int id, HotkeyModifiers modifiers, uint virtualKey)
        => RegisterHotKeyRaw(hWnd, id, (uint)modifiers, virtualKey);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool UnregisterHotKey(IntPtr hWnd, int id);

    // 字符串入参（类名/窗名）：按本仓库惯例走经典 DllImport + CharSet.Unicode，不用源生成器路线
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string? className, string? windowName);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool EnumDisplayMonitors(IntPtr hdc, IntPtr clipRect, MonitorEnumProc proc, IntPtr data);

    /// <summary>销毁 shell 分配的图标副本。仅对 TryGetExeIcon 一类"副本"句柄使用——
    /// WM_GETICON/GetClassLong 返回的是窗口自有句柄，绝不能销毁。</summary>
    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool DestroyIcon(IntPtr hIcon);

    /// <summary>
    /// 设进程显式 AUMID（真实导出名无 W 后缀）。必须先于任何窗口创建、每进程仅一次；
    /// 返回 HRESULT，S_OK=0。设了它任务栏身份不再被指向本 exe 的快捷方式按目标路径
    /// 隐式匹配接管——有关联时任务栏图标以快捷方式为准，运行时 WM_SETICON 换图标无效。
    /// </summary>
    [LibraryImport("shell32.dll", StringMarshalling = StringMarshalling.Utf16)]
    public static partial int SetCurrentProcessExplicitAppUserModelID(string appId);

    /// <summary>SW_RESTORE 还原窗口（最小化/最大化态恢复原样）。</summary>
    public static void RestoreWindow(IntPtr hwnd) => ShowWindowRaw(hwnd, SW_RESTORE);

    /// <summary>最小化则还原（吸附前的常规准备；最大化窗口不动）。</summary>
    public static void RestoreIfMinimized(IntPtr hwnd)
    {
        if (IsIconic(hwnd)) RestoreWindow(hwnd);
    }

    // ---------- z 序与落位（SetWindowPos 封装：旗标组合内藏，NOOWNERZORDER 恒带） ----------
    // SWP_NOOWNERZORDER 必带的坑（见 AGENTS）：缺了它移动子窗口会联动重排 owner 链——
    // VS Code 隐藏终端窗（PseudoConsoleWindow，owner=code）被系统拖进宿主正下方槽位，
    // 与 250ms 自愈永久互搏 = 中线闪烁。对无 owner / 带 NOZORDER 的调用它同样无害，
    // 故所有组合统一携带。绝不用 HWND_TOP 拉起子窗口（Alt+Tab 切回宿主后是静默无效调用）。

    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOZORDER = 0x0004;
    private const uint SWP_NOACTIVATE = 0x0010;
    private const uint SWP_FRAMECHANGED = 0x0020;
    private const uint SWP_NOOWNERZORDER = 0x0200;

    private const uint SWP_Z_ONLY = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER;
    private const uint SWP_MOVE_ONLY = SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER;
    private const uint SWP_SIZE_ONLY = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER;

    /// <summary>只改 z 序（不动几何、不激活）。预设位：Topmost / NotTopmost / Top。</summary>
    public static bool SetZOrder(IntPtr hwnd, ZOrderPosition position)
        => SetWindowPosRaw(hwnd, new IntPtr((int)position), 0, 0, 0, 0, SWP_Z_ONLY);

    /// <summary>只改 z 序，插到指定窗口正下方（子窗口吸附插入点 = 宿主正下方）。</summary>
    public static bool SetZOrderBelow(IntPtr hwnd, IntPtr insertBelow)
        => SetWindowPosRaw(hwnd, insertBelow, 0, 0, 0, 0, SWP_Z_ONLY);

    /// <summary>只移动不改尺寸不改 z 序（物理像素）。</summary>
    public static bool MoveWindowTo(IntPtr hwnd, int x, int y)
        => SetWindowPosRaw(hwnd, IntPtr.Zero, x, y, 0, 0, SWP_MOVE_ONLY);

    /// <summary>只改尺寸不移动不改 z 序（物理像素）。</summary>
    public static bool SizeWindowTo(IntPtr hwnd, int width, int height)
        => SetWindowPosRaw(hwnd, IntPtr.Zero, 0, 0, width, height, SWP_SIZE_ONLY);

    /// <summary>全量落位（保持现有 z 序；默认无激活——后台摆窗不打断前台焦点）。</summary>
    public static bool PlaceWindowIn(IntPtr hwnd, int x, int y, int width, int height, bool activate = false)
        => SetWindowPosRaw(hwnd, IntPtr.Zero, x, y, width, height,
            SWP_NOZORDER | SWP_NOOWNERZORDER | (activate ? 0 : SWP_NOACTIVATE));

    /// <summary>全量落位并插到指定窗口正下方（子窗口放格子专用：宿主不透明部分盖住
    /// 隐形边，透明格子透出子窗口）。默认无激活。</summary>
    public static bool PlaceWindowBelow(IntPtr hwnd, int x, int y, int width, int height, IntPtr insertBelow, bool activate = false)
        => SetWindowPosRaw(hwnd, insertBelow, x, y, width, height,
            SWP_NOOWNERZORDER | (activate ? 0 : SWP_NOACTIVATE));

    // ---------- 读取器（Try* 约定：false = 调用失败/拿不到，out 值勿用） ----------

    public static bool TryGetWindowRect(IntPtr hwnd, out RECT rect)
        => GetWindowRectRaw(hwnd, out rect);

    public static bool TryGetCursorPos(out POINT pt)
        => GetCursorPosRaw(out pt);

    /// <summary>显示器信息（cbSize 仪式内藏）。rcMonitor=整屏 / rcWork=工作区，物理像素。</summary>
    public static bool TryGetMonitorInfo(IntPtr hMonitor, out MONITORINFO info)
    {
        info = new MONITORINFO { cbSize = Marshal.SizeOf<MONITORINFO>() };
        return GetMonitorInfoRaw(hMonitor, ref info);
    }

    /// <summary>窗口的还原矩形（非最小化/最大化时的正常几何，WINDOWPLACEMENT 通道）。</summary>
    public static bool TryGetRestoreRect(IntPtr hwnd, out RECT rect)
    {
        var pl = new WINDOWPLACEMENT { length = Marshal.SizeOf<WINDOWPLACEMENT>() };
        if (GetWindowPlacementRaw(hwnd, ref pl))
        {
            rect = pl.rcNormalPosition;
            return true;
        }
        rect = default;
        return false;
    }

    /// <summary>扩展样式位测试（GWL_EXSTYLE 域）。</summary>
    public static bool HasExStyle(IntPtr hwnd, WindowExStyles style)
        => (GetWindowLongRaw(hwnd, GWL_EXSTYLE) & (int)style) != 0;

    /// <summary>关系查询：z 序下一个窗口 / owner 窗口。</summary>
    public static IntPtr GetRelatedWindow(IntPtr hwnd, GetWindowRelation relation)
        => GetWindowRaw(hwnd, (int)relation);

    /// <summary>DWM 扩展框架边界（可见窗口矩形，不含 ~7px 隐形边）。</summary>
    public static bool TryGetExtendedFrameBounds(IntPtr hwnd, out RECT rect)
        => DwmGetWindowAttributeRectRaw(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, out rect, Marshal.SizeOf<RECT>()) == 0;

    /// <summary>Win11 DWM 圆角是否被吸附流程直角化过（DONOTROUND；也是孤儿记录的吸附态特征）。
    /// Win10 无此属性返回 false。</summary>
    public static bool HasSquareCorners(IntPtr hwnd)
        => DwmGetWindowAttributeRaw(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, out int pref, sizeof(int)) == 0
            && pref == DWMWCP_DONOTROUND;

    // ---------- 显示器（MONITOR_DEFAULTTONEAREST 语义内藏） ----------

    public static IntPtr MonitorNearestFromPoint(POINT pt)
        => MonitorFromPointRaw(pt, MONITOR_DEFAULTTONEAREST);

    public static IntPtr MonitorNearestFromWindow(IntPtr hwnd)
        => MonitorFromWindowRaw(hwnd, MONITOR_DEFAULTTONEAREST);

    // ---------- 图标（所有权边界内藏在各方法文档里） ----------

    private const uint WM_GETICON = 0x007F;
    private const int GCLP_HICON = -14;
    private const int GCLP_HICONSM = -34;

    /// <summary>窗口自有图标（WM_GETICON 通道）。返回的 HICON 是窗口自有的句柄（非副本），
    /// 调用方绝不能 DestroyIcon。</summary>
    public static bool TryGetWindowIcon(IntPtr hwnd, IconKind kind, out IntPtr hIcon)
    {
        hIcon = SendMessageRaw(hwnd, WM_GETICON, new IntPtr((int)kind), IntPtr.Zero);
        return hIcon != IntPtr.Zero;
    }

    /// <summary>窗口类图标（GetClassLong 通道）。返回的 HICON 是窗口自有的句柄（非副本），
    /// 调用方绝不能 DestroyIcon。</summary>
    public static bool TryGetClassIcon(IntPtr hwnd, IconKind kind, out IntPtr hIcon)
    {
        int index = kind == IconKind.Big ? GCLP_HICON : GCLP_HICONSM;
        hIcon = new IntPtr(GetClassLongRaw(hwnd, index));
        return hIcon != IntPtr.Zero;
    }

    private const uint SHGFI_ICON = 0x0100;
    private const uint SHGFI_LARGEICON = 0x0000;
    private const uint FILE_ATTRIBUTE_NORMAL = 0x0080;

    /// <summary>按 exe 路径取 shell 大图标。返回的 HICON 是 shell 分配的副本，
    /// 调用方用完必须 DestroyIcon（snap 接管：UWP/框架窗窗口本身无图标素材的兜底通道）。</summary>
    public static bool TryGetExeIcon(string exePath, out IntPtr hIcon)
    {
        var shfi = new SHFILEINFOW();
        if (SHGetFileInfoW(exePath, FILE_ATTRIBUTE_NORMAL, ref shfi,
                (uint)Marshal.SizeOf<SHFILEINFOW>(), SHGFI_ICON | SHGFI_LARGEICON) != IntPtr.Zero)
        {
            hIcon = shfi.hIcon;
            return true;
        }
        hIcon = IntPtr.Zero;
        return false;
    }

    /// <summary>任务栏大图标目标画布尺寸（PMv2 进程下随 DPI 缩放：32px@100% ↔ 48px@150%）。
    /// 图标按本征尺寸绘制、shell 不放大——固定 32px 画布在高 DPI 上比周边应用小一圈。</summary>
    public static (int Width, int Height) IconCanvasSize()
    {
        int w = GetSystemMetrics(SM_CXICON);
        int h = GetSystemMetrics(SM_CYICON);
        return (w > 0 ? w : 32, h > 0 ? h : 32);
    }

    // ---------- WinEvent 全局钩子（OUTOFCONTEXT|SKIPOWNPROCESS 内藏；回调须调用方保活） ----------

    public static IntPtr HookWindowEvents(SystemEvent minEvent, SystemEvent maxEvent, WinEventProc proc)
        => SetWinEventHookRaw((uint)minEvent, (uint)maxEvent, IntPtr.Zero, proc, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS);

    public static bool UnhookWindowEvents(IntPtr hook)
        => UnhookWinEventRaw(hook);

    // ---------- 字符串 / DPI / 进程（既有 C# 友好层） ----------

    public static string GetTitle(IntPtr hwnd)
    {
        int len = GetWindowTextLength(hwnd);
        if (len <= 0) return string.Empty;
        var sb = new StringBuilder(len + 1);
        GetWindowText(hwnd, sb, sb.Capacity);
        return sb.ToString();
    }

    public static string GetClassNameOf(IntPtr hwnd)
    {
        var sb = new StringBuilder(256);
        GetClassName(hwnd, sb, sb.Capacity);
        return sb.ToString();
    }

    public static bool IsCloaked(IntPtr hwnd)
        => DwmGetWindowAttributeRaw(hwnd, DWMWA_CLOAKED, out int cloaked, sizeof(int)) == 0 && cloaked != 0;

    public static uint GetPid(IntPtr hwnd)
    {
        GetWindowThreadProcessId(hwnd, out uint pid);
        return pid;
    }

    /// <summary>显示器的有效 DPI（PMv2 进程返回真实缩放）。窗口未建 hwnd 时按目标屏换算几何用。</summary>
    public static double MonitorDpiScale(IntPtr hMonitor)
    {
        if (GetDpiForMonitor(hMonitor, 0 /* MDT_EFFECTIVE_DPI */, out uint dpiX, out _) != 0 || dpiX == 0) return SystemDpiScale();
        return dpiX / 96.0;
    }

    /// <summary>系统 DPI（PMv2 进程 = 会话启动时主屏 DPI）。无目标屏可查时的兜底缩放。</summary>
    public static double SystemDpiScale() => GetDpiForSystem() / 96.0;

    /// <summary>
    /// GetWindowRect 相对可见窗口（扩展框架边界）四侧的隐形边（Win11/DWM 边）。
    /// 吸附时按此值外扩目标矩形，可见内容才能精确填满格子。
    /// </summary>
    public static (int Left, int Top, int Right, int Bottom) GetInvisibleFrameMargins(IntPtr hwnd)
    {
        if (GetWindowRectRaw(hwnd, out RECT wr)
            && DwmGetWindowAttributeRectRaw(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, out RECT fb, Marshal.SizeOf<RECT>()) == 0)
        {
            int l = Math.Max(0, fb.Left - wr.Left);
            int t = Math.Max(0, fb.Top - wr.Top);
            int r = Math.Max(0, wr.Right - fb.Right);
            int b = Math.Max(0, wr.Bottom - fb.Bottom);
            return (l, t, r, b);
        }
        return (0, 0, 0, 0);
    }

    /// <summary>rootPid 的全部后代进程 PID（含间接后代；快照式，不含 rootPid 本身）。</summary>
    public static HashSet<int> GetDescendantProcessIds(int rootPid)
    {
        var result = new HashSet<int>();
        nint snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snap == nint.Zero || snap == new nint(-1)) return result;
        try
        {
            var pe = new PROCESSENTRY32W { dwSize = (uint)Marshal.SizeOf<PROCESSENTRY32W>() };
            if (!Process32First(snap, ref pe)) return result;
            var byParent = new Dictionary<uint, List<uint>>();
            do
            {
                if (!byParent.TryGetValue(pe.th32ParentProcessID, out var kids))
                {
                    byParent[pe.th32ParentProcessID] = kids = new List<uint>();
                }
                kids.Add(pe.th32ProcessID);
            }
            while (Process32Next(snap, ref pe));

            var queue = new Queue<uint>();
            queue.Enqueue((uint)rootPid);
            while (queue.Count > 0)
            {
                if (!byParent.TryGetValue(queue.Dequeue(), out var kids)) continue;
                foreach (var kid in kids)
                {
                    if (result.Add((int)kid)) queue.Enqueue(kid);
                }
            }
        }
        finally
        {
            CloseHandle(snap);
        }
        return result;
    }

    /// <summary>进程的可执行文件完整路径（镜像路径）；打不开进程（提权/受保护）返回 null。</summary>
    public static string? GetProcessImagePath(uint pid)
    {
        // PROCESS_QUERY_LIMITED_INFORMATION：跨完整性级别查询镜像路径的最低权限
        nint hProc = OpenProcess(0x1000, false, (int)pid);
        if (hProc == nint.Zero) return null;
        try
        {
            var sb = new StringBuilder(1024);
            int size = sb.Capacity;
            // 字符串出入参走经典 DllImport（LibraryImport 不支持 StringBuilder，见类头铁律②；
            // 必须 CharSet.Unicode——漏写会按 ANSI 反序列化，sb.Length 小于返回的 size，ToString 越界）
            if (!QueryFullProcessImageName(hProc, 0, sb, ref size) || size <= 0 || size > sb.Length) return null;
            return sb.ToString(0, size);
        }
        finally
        {
            CloseHandle(hProc);
        }
    }

    // ---------- 子窗口样式/外观封装（吸附架构专用） ----------

    /// <summary>
    /// 任务栏/Alt+Tab 收录开关（原 WS_EX_TOOLWINDOW 方案退役，吸附窗口从此保持普通样式）。
    /// DeleteTab 是 shell 侧运行时状态且无查询接口：explorer 重启会重建 task list 丢失
    /// 删除标记并使旧代理失效，吸附维护循环低频重断言兜底。shell 不可用（CoCreateInstance
    /// 失败）按设计静默——没有任务栏就没有"隐藏"可言。
    /// </summary>
    public static void SetTaskbarTab(IntPtr hwnd, bool show)
    {
        for (int attempt = 0; attempt < 2; attempt++) // 第二圈：旧代理失效复位后的重建重试
        {
            if (_taskbarPunk == IntPtr.Zero)
            {
                var clsid = TaskbarListClsid; // ref/out 不收 static readonly（CS0199），取局部副本
                var iid = TaskbarListIid;
                if (CoCreateInstance(ref clsid, IntPtr.Zero, CLSCTX_ALL,
                        ref iid, out _taskbarPunk) != 0)
                {
                    _taskbarPunk = IntPtr.Zero;
                    return;
                }
                if (CallTaskbarSlot(3, IntPtr.Zero) != 0) // HrInit 必须先于其他方法
                {
                    Marshal.Release(_taskbarPunk);
                    _taskbarPunk = IntPtr.Zero;
                    return;
                }
            }
            if (CallTaskbarSlot(show ? 4 : 5, hwnd) == 0) return;
            Marshal.Release(_taskbarPunk); // explorer 重启后旧实例失效：复位重建后重试一次
            _taskbarPunk = IntPtr.Zero;
        }
    }

    /// <summary>Win11 DWM 圆角开关：吸附时直角化（DONOTROUND）防"圆角缝"，释放还原 DEFAULT。Win10 无此属性，调用失败无副作用。</summary>
    public static void SetSquareCorners(IntPtr hwnd, bool square)
    {
        int pref = square ? DWMWCP_DONOTROUND : DWMWCP_DEFAULT;
        DwmSetWindowAttributeRaw(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ref pref, sizeof(int));
    }

    /// <summary>子窗吸附期间摘掉可缩放边框（WS_THICKFRAME）：禁掉用户拖子窗边缘改大小
    /// （格子尺寸由宿主全权管理），释放时还原。样式变更带 SWP_FRAMECHANGED 触发非客户区
    /// 重算；无变化时是 no-op（维护周期重断言路径）。UIPI 下失败静默（与吸附其他样式操作同口径）。</summary>
    public static void SetResizable(IntPtr hwnd, bool resizable)
    {
        int style = GetWindowLongRaw(hwnd, GWL_STYLE);
        bool has = (style & WS_THICKFRAME) != 0;
        if (resizable == has) return;
        style = resizable ? style | WS_THICKFRAME : style & ~WS_THICKFRAME;
        SetWindowLongRaw(hwnd, GWL_STYLE, style);
        SetWindowPosRaw(hwnd, IntPtr.Zero, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
    }

    // ---------- 窗口级 AUMID（SHGetPropertyStoreForWindow + IPropertyStore 裸 vtable） ----------
    // 多扇平级宿主各写唯一 System.AppUserModel.ID：shell 任务栏按钮按 AUMID 分组，不同
    // AUMID = 各自独立按钮（不受用户"合并任务栏按钮"设置影响）。必须赶在窗口可见前设置
    // （OnSourceInitialized 时机）。同一裸 vtable 模式（PKEY/PROPVARIANT 全走 IntPtr，
    // 无封送风险）；IPropertyStore 槽位：0=QI 1=AddRef 2=Release 3=GetCount 4=GetAt
    // 5=GetValue 6=SetValue 7=Commit。失败按设计静默（退回进程级 AUMID 的合并表现）。

    /// <summary>给窗口设独立 AppUserModel.ID（任务栏独立按钮）。返回诊断串（写入/读回结果，
    /// HostWindow 侧 WM_TRACE 落盘）；失败静默不抛（退回进程级合并表现）。</summary>
    public static string SetWindowAppUserModelId(IntPtr hwnd, string aumid)
    {
        var iid = PropertyStoreIid;
        int storeHr = SHGetPropertyStoreForWindow(hwnd, ref iid, out IntPtr store);
        if (storeHr != 0 || store == IntPtr.Zero)
            return $"GetStore hr=0x{storeHr:X8} store={store}";
        IntPtr keyPtr = IntPtr.Zero, propPtr = IntPtr.Zero, strPtr = IntPtr.Zero;
        try
        {
            keyPtr = Marshal.AllocHGlobal(Marshal.SizeOf<PROPERTYKEY>());
            Marshal.StructureToPtr(new PROPERTYKEY { fmtid = AppUserModelFmtid, pid = 5 }, keyPtr, false);
            propPtr = Marshal.AllocHGlobal(Marshal.SizeOf<PROPVARIANT>());
            strPtr = Marshal.StringToCoTaskMemUni(aumid);
            Marshal.StructureToPtr(new PROPVARIANT { vt = VT_LPWSTR, pwszVal = strPtr }, propPtr, false);
            strPtr = IntPtr.Zero; // 所有权已随 PROPVARIANT 交给 PropVariantClear

            var vtbl = Marshal.ReadIntPtr(store);
            var getValue = Marshal.GetDelegateForFunctionPointer<PropStoreFn3>(Marshal.ReadIntPtr(vtbl, 5 * IntPtr.Size));
            var setValue = Marshal.GetDelegateForFunctionPointer<PropStoreFn3>(Marshal.ReadIntPtr(vtbl, 6 * IntPtr.Size));
            var commit = Marshal.GetDelegateForFunctionPointer<PropStoreFn1>(Marshal.ReadIntPtr(vtbl, 7 * IntPtr.Size));
            int setHr = setValue(store, keyPtr, propPtr);
            int commitHr = setHr == 0 ? commit(store) : -1;
            // 写入后读回验证（诊断串；失败静默不回滚——退回进程级合并表现）
            string readBack;
            if (setHr == 0 && commitHr == 0)
            {
                IntPtr outPtr = Marshal.AllocHGlobal(Marshal.SizeOf<PROPVARIANT>());
                try
                {
                    Marshal.StructureToPtr(new PROPVARIANT(), outPtr, false);
                    int getHr = getValue(store, keyPtr, outPtr);
                    readBack = getHr == 0
                        ? Marshal.PtrToStringUni(Marshal.ReadIntPtr(outPtr, 8)) ?? "<null>"
                        : $"hr=0x{getHr:X8}";
                    PropVariantClear(outPtr);
                }
                finally { Marshal.FreeHGlobal(outPtr); }
            }
            else
            {
                readBack = "-";
            }
            return $"set=0x{setHr:X8} commit=0x{commitHr:X8} readBack={readBack}";
        }
        finally
        {
            if (propPtr != IntPtr.Zero) PropVariantClear(propPtr); // 释放 VT_LPWSTR 的 pwszVal
            if (strPtr != IntPtr.Zero) Marshal.FreeCoTaskMem(strPtr);
            if (keyPtr != IntPtr.Zero) Marshal.FreeHGlobal(keyPtr);
            if (propPtr != IntPtr.Zero) Marshal.FreeHGlobal(propPtr);
            Marshal.Release(store);
        }
    }

    // ---------- 私有 raw 导入区（签名与原生一致，文件外禁调） ----------

    private const int SM_CXICON = 11; // 任务栏大图标（PMv2 进程返回随 DPI 缩放的值）
    private const int SM_CYICON = 12;

    private const int SW_RESTORE = 9; // ShowWindow

    // GetWindowLong / SetWindowLong 域
    private const int GWL_STYLE = -16;
    private const int GWL_EXSTYLE = -20;
    private const int WS_THICKFRAME = 0x00040000;

    // DWM 属性
    private const int DWMWA_CLOAKED = 14;
    private const int DWMWA_EXTENDED_FRAME_BOUNDS = 9;
    private const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
    private const int DWMWCP_DEFAULT = 0;
    private const int DWMWCP_DONOTROUND = 1;

    private const int MONITOR_DEFAULTTONEAREST = 2;

    private const uint TH32CS_SNAPPROCESS = 0x00000002;

    private const uint WINEVENT_OUTOFCONTEXT = 0x0;
    private const uint WINEVENT_SKIPOWNPROCESS = 0x2;

    [LibraryImport("user32.dll", EntryPoint = "RegisterHotKey")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool RegisterHotKeyRaw(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [LibraryImport("user32.dll", EntryPoint = "SetWindowPos", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool SetWindowPosRaw(IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint uFlags);

    [LibraryImport("user32.dll", EntryPoint = "GetWindowRect")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetWindowRectRaw(IntPtr hWnd, out RECT lpRect);

    [LibraryImport("user32.dll", EntryPoint = "GetCursorPos")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetCursorPosRaw(out POINT lpPoint);

    [LibraryImport("user32.dll", EntryPoint = "ShowWindow")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool ShowWindowRaw(IntPtr hWnd, int nCmdShow);

    [LibraryImport("user32.dll", EntryPoint = "GetWindowPlacement")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetWindowPlacementRaw(IntPtr hWnd, ref WINDOWPLACEMENT lpwndpl);

    [LibraryImport("user32.dll", EntryPoint = "GetWindowLongW")]
    private static partial int GetWindowLongRaw(IntPtr hWnd, int nIndex);

    [LibraryImport("user32.dll", EntryPoint = "SetWindowLongW")]
    private static partial int SetWindowLongRaw(IntPtr hWnd, int nIndex, int dwNewLong);

    [LibraryImport("user32.dll", EntryPoint = "SendMessageW")]
    private static partial IntPtr SendMessageRaw(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [LibraryImport("user32.dll", EntryPoint = "GetClassLongW")]
    private static partial int GetClassLongRaw(IntPtr hWnd, int nIndex);

    [LibraryImport("user32.dll", EntryPoint = "GetWindow")]
    private static partial IntPtr GetWindowRaw(IntPtr hWnd, int nCmd);

    [LibraryImport("user32.dll")]
    public static partial IntPtr GetTopWindow(IntPtr hWnd);

    [LibraryImport("user32.dll")]
    private static partial uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [LibraryImport("user32.dll", EntryPoint = "GetMonitorInfoW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetMonitorInfoRaw(IntPtr hMonitor, ref MONITORINFO lpmi);

    [LibraryImport("user32.dll", EntryPoint = "MonitorFromWindow")]
    private static partial IntPtr MonitorFromWindowRaw(IntPtr hwnd, int dwFlags);

    [LibraryImport("user32.dll", EntryPoint = "MonitorFromPoint")]
    private static partial IntPtr MonitorFromPointRaw(POINT pt, int dwFlags);

    [LibraryImport("user32.dll")]
    private static partial int GetSystemMetrics(int nIndex);

    [LibraryImport("user32.dll", EntryPoint = "SetWinEventHook")]
    private static partial IntPtr SetWinEventHookRaw(uint eventMin, uint eventMax, IntPtr hmodWinEventProc, WinEventProc pfnWinEventProc, uint idProcess, uint idThread, uint dwFlags);

    [LibraryImport("user32.dll", EntryPoint = "UnhookWinEvent")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool UnhookWinEventRaw(IntPtr hWinEventHook);

    [LibraryImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")]
    private static partial int DwmGetWindowAttributeRaw(IntPtr hwnd, int dwAttribute, out int pvAttribute, int cbAttribute);

    [LibraryImport("dwmapi.dll", EntryPoint = "DwmSetWindowAttribute")]
    private static partial int DwmSetWindowAttributeRaw(IntPtr hwnd, int dwAttribute, ref int pvAttribute, int cbAttribute);

    [LibraryImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")]
    private static partial int DwmGetWindowAttributeRectRaw(IntPtr hwnd, int dwAttribute, out RECT pvAttribute, int cbAttribute);

    [LibraryImport("shcore.dll")]
    private static partial int GetDpiForMonitor(IntPtr hMonitor, int dpiType, out uint dpiX, out uint dpiY);

    [LibraryImport("user32.dll")]
    private static partial uint GetDpiForSystem();

    // 源生成 P/Invoke 不支持 StringBuilder 参数，字符串出入参走经典 DllImport（类头铁律②）
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", EntryPoint = "GetWindowTextLengthW")]
    private static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [StructLayout(LayoutKind.Sequential)]
    private struct WINDOWPLACEMENT
    {
        public int length, flags, showCmd;
        public POINT ptMinPosition, ptMaxPosition;
        public RECT rcNormalPosition;
    }

    // shell exe 图标：SHGetFileInfoW（snap 接管兜底通道，见 TryGetExeIcon）
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct SHFILEINFOW
    {
        public IntPtr hIcon;
        public int iIcon;
        public uint dwAttributes;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szDisplayName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 80)]
        public string szTypeName;
    }

    // 字符串入参（路径）：按本仓库惯例走经典 DllImport + CharSet.Unicode，不用源生成器路线
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr SHGetFileInfoW(string pszPath, uint dwFileAttributes,
        ref SHFILEINFOW psfi, uint cbFileInfo, uint uFlags);

    // 进程快照（GetDescendantProcessIds / GetProcessImagePath）
    [LibraryImport("kernel32.dll", SetLastError = true)]
    private static partial nint CreateToolhelp32Snapshot(uint dwFlags, uint th32ProcessID);

    [LibraryImport("kernel32.dll", SetLastError = true, EntryPoint = "Process32FirstW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool Process32First(nint hSnapshot, ref PROCESSENTRY32W lppe);

    [LibraryImport("kernel32.dll", SetLastError = true, EntryPoint = "Process32NextW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool Process32Next(nint hSnapshot, ref PROCESSENTRY32W lppe);

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(nint hObject);

    [StructLayout(LayoutKind.Sequential)]
    private unsafe struct PROCESSENTRY32W
    {
        public uint dwSize;
        public uint cntUsage;
        public uint th32ProcessID;
        public nint th32DefaultHeapID;
        public uint th32ModuleID;
        public uint cntThreads;
        public uint th32ParentProcessID;
        public long pcPriClassBase;
        public uint dwFlags;
        public fixed char szExeFile[260];
    }

    [LibraryImport("kernel32.dll", SetLastError = true)]
    private static partial nint OpenProcess(uint dwDesiredAccess, [MarshalAs(UnmanagedType.Bool)] bool bInheritHandle, int dwProcessId);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "QueryFullProcessImageNameW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageName(nint hProcess, int dwFlags, StringBuilder lpExeName, ref int lpdwSize);

    // ---------- 任务栏 tab（ITaskbarList 裸 vtable：DeleteTab/AddTab 隐藏与恢复任务栏/Alt+Tab，不改窗口样式） ----------
    // 走 Marshal 裸 vtable 而非 [ComImport] 内建 interop：.NET 10 编译器拒收 co-class→接口转换
    // （CS0030，与 IShellLinkW 字符串封送 ArgumentException 同为内建 interop 的坑）；
    // 接口只有 IntPtr 参数，裸调用无封送风险。仅 UI 线程调用（WPF 主线程已是 STA）。

    private static readonly Guid TaskbarListClsid = new("56FDF344-FD6D-11d0-958A-006097C9A090");
    private static readonly Guid TaskbarListIid = new("56FDF342-FD6D-11d0-958A-006097C9A090");
    private const uint CLSCTX_ALL = 23;

    private static IntPtr _taskbarPunk; // ITaskbarList 实例（vtable 槽位：3=HrInit 4=AddTab 5=DeleteTab）

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int TaskbarListFn(IntPtr self, IntPtr hwnd);

    [LibraryImport("ole32")]
    private static partial int CoCreateInstance(ref Guid rclsid, IntPtr pUnkOuter, uint dwClsContext, ref Guid riid, out IntPtr ppv);

    private static int CallTaskbarSlot(int slot, IntPtr hwnd)
    {
        var vtbl = Marshal.ReadIntPtr(_taskbarPunk);
        var fn = Marshal.GetDelegateForFunctionPointer<TaskbarListFn>(Marshal.ReadIntPtr(vtbl, slot * IntPtr.Size));
        return fn(_taskbarPunk, hwnd);
    }

    private static readonly Guid PropertyStoreIid = new("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF4C"); // IPropertyStore
    private static readonly Guid AppUserModelFmtid = new("9F4C2855-9FDB-464B-8129-29B3D31E2C5A"); // PKEY_AppUserModel_ID
    private const ushort VT_LPWSTR = 31;

    [StructLayout(LayoutKind.Sequential)]
    private struct PROPERTYKEY
    {
        public Guid fmtid;
        public uint pid;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PROPVARIANT
    {
        public ushort vt;
        public ushort r1;
        public ushort r2;
        public ushort r3;
        public IntPtr pwszVal; // VT_LPWSTR 联合体成员
    }

    [DllImport("propsys.dll", EntryPoint = "#4")] // 真实实现按 ordinal 4 导出（无名字）——
    private static extern int SHGetPropertyStoreForWindow(IntPtr hwnd, ref Guid iid, out IntPtr ppv);
    // shell32 的同名导出在本机（Win11 26300）是坏 stub：IUnknown 都返回 E_NOINTERFACE，
    // propsys ordinal 4 才是真身（dumpbin 实锤）。python ctypes 同机同样复现。

    [LibraryImport("ole32")]
    private static partial int PropVariantClear(IntPtr pvar);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int PropStoreFn3(IntPtr self, IntPtr a, IntPtr b); // SetValue / GetValue

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int PropStoreFn2(IntPtr self, IntPtr a); // GetCount 类（预留）

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int PropStoreFn1(IntPtr self); // Commit / Release
}
