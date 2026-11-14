using System.Runtime.InteropServices;
using System.Text;

namespace WindowMerger;

internal static partial class Native
{
    public delegate void WinEventProc(IntPtr hWinEventHook, uint @event, IntPtr hwnd, int idObject, int idChild, uint idEventThread, uint dwmsEventTime);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

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
    public struct WINDOWPLACEMENT
    {
        public int length, flags, showCmd;
        public POINT ptMinPosition, ptMaxPosition;
        public RECT rcNormalPosition;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MONITORINFO
    {
        public int cbSize;
        public RECT rcMonitor;
        public RECT rcWork;
        public int dwFlags;
    }

    // SetWindowPos
    public const uint SWP_NOSIZE = 0x0001;
    public const uint SWP_NOMOVE = 0x0002;
    public const uint SWP_NOZORDER = 0x0004;
    public const uint SWP_NOACTIVATE = 0x0010;
    public const uint SWP_NOOWNERZORDER = 0x0200;

    // 置顶带（IntPtr 不能作 const，用 static readonly）
    public static readonly IntPtr HwndTopmost = new(-1);
    public static readonly IntPtr HwndNotTopmost = new(-2);
    public static readonly IntPtr HwndTop = new(0);

    // GetWindowLong / GetWindow
    public const int GWL_EXSTYLE = -20;
    public const int WS_EX_TOOLWINDOW = 0x00000080;
    public const int WS_EX_TRANSPARENT = 0x00000020;
    public const int GW_OWNER = 4;
    public const int GW_HWNDNEXT = 2;

    // 任务栏大图标尺寸（PMv2 进程返回随 DPI 缩放的值：32px@100% ↔ 48px@150%）
    public const int SM_CXICON = 11;
    public const int SM_CYICON = 12;

    [LibraryImport("user32.dll")]
    public static partial int GetSystemMetrics(int nIndex);

    // ShowWindow
    public const int SW_HIDE = 0;
    public const int SW_MINIMIZE = 6;
    public const int SW_SHOWNA = 8;
    public const int SW_RESTORE = 9;

    // 图标
    public const uint WM_GETICON = 0x007F;
    public const int ICON_BIG = 1;
    public const int ICON_SMALL2 = 2;
    public const int GCLP_HICON = -14;
    public const int GCLP_HICONSM = -34;

    // shell exe 图标（snap 接管：UWP/框架窗窗口本身无图标素材——实测设置窗四连全 miss，
    // shell 的按钮图标走 app tile——按进程 exe 兜底；框架窗经子 CoreWindow 找真实应用进程）
    public const uint SHGFI_ICON = 0x0100;
    public const uint SHGFI_LARGEICON = 0x0000;
    public const uint FILE_ATTRIBUTE_NORMAL = 0x0080;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct SHFILEINFOW
    {
        public IntPtr hIcon;
        public int iIcon;
        public uint dwAttributes;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szDisplayName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 80)]
        public string szTypeName;
    }

    // 字符串入参（路径/类名）：按本仓库惯例走经典 DllImport + CharSet.Unicode，不用源生成器路线
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr SHGetFileInfoW(string pszPath, uint dwFileAttributes,
        ref SHFILEINFOW psfi, uint cbFileInfo, uint uFlags);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string? className, string? windowName);

    /// <summary>
    /// 设进程显式 AUMID（真实导出名无 W 后缀）。必须先于任何窗口创建、每进程仅一次；
    /// 返回 HRESULT，S_OK=0。设了它任务栏身份不再被指向本 exe 的快捷方式按目标路径
    /// 隐式匹配接管——有关联时任务栏图标以快捷方式为准，运行时 WM_SETICON 换图标无效。
    /// </summary>
    [LibraryImport("shell32.dll", StringMarshalling = StringMarshalling.Utf16)]
    public static partial int SetCurrentProcessExplicitAppUserModelID(string appId);

    // DWM
    public const int DWMWA_CLOAKED = 14;
    public const int DWMWA_EXTENDED_FRAME_BOUNDS = 9;
    public const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
    public const int DWMWCP_DEFAULT = 0;
    public const int DWMWCP_DONOTROUND = 1;

    // 进程快照
    public const uint TH32CS_SNAPPROCESS = 0x00000002;

    // WinEvent
    public const uint EVENT_SYSTEM_FOREGROUND = 0x0003;
    public const uint EVENT_SYSTEM_MOVESIZE = 0x000A;
    public const uint EVENT_SYSTEM_MOVESIZEEND = 0x000B;
    public const uint WINEVENT_OUTOFCONTEXT = 0x0;
    public const uint WINEVENT_SKIPOWNPROCESS = 0x2;
    public const int OBJID_WINDOW = 0;

    public const int MONITOR_DEFAULTTONEAREST = 2;

    // 全局热键 / 前台窗口 / 显示器枚举（snap 接管：托盘热键与布局检测用。
    // 这三个 API 无 A/W 变体，导出名即方法名，无需 EntryPoint 显式指名）
    public const uint MOD_ALT = 0x0001;
    public const uint MOD_CONTROL = 0x0002;
    public const uint MOD_SHIFT = 0x0004;
    public const uint MOD_WIN = 0x0008;

    [LibraryImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool UnregisterHotKey(IntPtr hWnd, int id);

    [LibraryImport("user32.dll")]
    public static partial IntPtr GetForegroundWindow();

    /// <summary>把前台转交给指定窗口。调用方须持有前台（否则被前台锁静默拒绝），
    /// 返回 false = 被拒（前台锁/UIPI），不致命。</summary>
    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool SetForegroundWindow(IntPtr hWnd);

    public delegate bool MonitorEnumProc(IntPtr hMonitor, IntPtr hdc, ref RECT rect, IntPtr data);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool EnumDisplayMonitors(IntPtr hdc, IntPtr clipRect, MonitorEnumProc proc, IntPtr data);

    [LibraryImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint uFlags);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool GetCursorPos(out POINT lpPoint);

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
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool GetWindowPlacement(IntPtr hWnd, ref WINDOWPLACEMENT lpwndpl);

    [LibraryImport("user32.dll", EntryPoint = "GetWindowLongW")]
    public static partial int GetWindowLong(IntPtr hWnd, int nIndex);

    [LibraryImport("user32.dll", EntryPoint = "SetWindowLongW")]
    public static partial int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

    [LibraryImport("user32.dll", EntryPoint = "SendMessageW")]
    public static partial IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [LibraryImport("user32.dll", EntryPoint = "GetClassLongW")]
    public static partial int GetClassLong(IntPtr hWnd, int nIndex);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool DestroyIcon(IntPtr hIcon);

    [LibraryImport("user32.dll")]
    public static partial IntPtr GetWindow(IntPtr hWnd, int nCmd);

    [LibraryImport("user32.dll")]
    public static partial IntPtr GetTopWindow(IntPtr hWnd);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    // 源生成 P/Invoke 不支持 StringBuilder 参数，这两个走经典 DllImport
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [LibraryImport("user32.dll", EntryPoint = "GetWindowTextLengthW")]
    public static partial int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

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
            // 字符串出入参走经典 DllImport（LibraryImport 不支持 StringBuilder，见 AGENTS.md；
            // 必须 CharSet.Unicode——漏写会按 ANSI 反序列化，sb.Length 小于返回的 size，ToString 越界）
            if (!QueryFullProcessImageName(hProc, 0, sb, ref size) || size <= 0 || size > sb.Length) return null;
            return sb.ToString(0, size);
        }
        finally
        {
            CloseHandle(hProc);
        }
    }

    [LibraryImport("kernel32.dll", SetLastError = true)]
    private static partial nint OpenProcess(uint dwDesiredAccess, [MarshalAs(UnmanagedType.Bool)] bool bInheritHandle, int dwProcessId);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "QueryFullProcessImageNameW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageName(nint hProcess, int dwFlags, StringBuilder lpExeName, ref int lpdwSize);

    [LibraryImport("user32.dll")]
    public static partial uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [LibraryImport("dwmapi.dll")]
    public static partial int DwmGetWindowAttribute(IntPtr hwnd, int dwAttribute, out int pvAttribute, int cbAttribute);

    [LibraryImport("dwmapi.dll")]
    public static partial int DwmSetWindowAttribute(IntPtr hwnd, int dwAttribute, ref int pvAttribute, int cbAttribute);

    [LibraryImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")]
    public static partial int DwmGetWindowAttributeRect(IntPtr hwnd, int dwAttribute, out RECT pvAttribute, int cbAttribute);

    [LibraryImport("user32.dll")]
    public static partial IntPtr SetWinEventHook(uint eventMin, uint eventMax, IntPtr hmodWinEventProc, WinEventProc pfnWinEventProc, uint idProcess, uint idThread, uint dwFlags);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool UnhookWinEvent(IntPtr hWinEventHook);

    [LibraryImport("user32.dll")]
    public static partial IntPtr MonitorFromWindow(IntPtr hwnd, int dwFlags);

    // MonitorFromPoint 的兜底语义：MONITOR_DEFAULTTONEAREST 见常量区（=2）
    public const int MONITOR_DEFAULTTOPRIMARY = 1;

    [LibraryImport("user32.dll")]
    public static partial IntPtr MonitorFromPoint(POINT pt, int dwFlags);

    /// <summary>显示器的有效 DPI（PMv2 进程返回真实缩放）。窗口未建 hwnd 时按目标屏换算几何用。</summary>
    public static double MonitorDpiScale(IntPtr hMonitor)
    {
        if (GetDpiForMonitor(hMonitor, 0 /* MDT_EFFECTIVE_DPI */, out uint dpiX, out _) != 0 || dpiX == 0) return SystemDpiScale();
        return dpiX / 96.0;
    }

    [LibraryImport("shcore.dll")]
    private static partial int GetDpiForMonitor(IntPtr hMonitor, int dpiType, out uint dpiX, out uint dpiY);

    /// <summary>系统 DPI（PMv2 进程 = 会话启动时主屏 DPI）。无目标屏可查时的兜底缩放。</summary>
    public static double SystemDpiScale() => GetDpiForSystem() / 96.0;

    [LibraryImport("user32.dll")]
    private static partial uint GetDpiForSystem();

    [LibraryImport("user32.dll", EntryPoint = "GetMonitorInfoW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static partial bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFO lpmi);

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
        => DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, out int cloaked, sizeof(int)) == 0 && cloaked != 0;

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
        DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ref pref, sizeof(int));
    }

    public static uint GetPid(IntPtr hwnd)
    {
        GetWindowThreadProcessId(hwnd, out uint pid);
        return pid;
    }

    /// <summary>
    /// GetWindowRect 相对可见窗口（扩展框架边界）四侧的隐形边（Win11/DWM 边）。
    /// 吸附时按此值外扩目标矩形，可见内容才能精确填满格子。
    /// </summary>
    public static (int Left, int Top, int Right, int Bottom) GetInvisibleFrameMargins(IntPtr hwnd)
    {
        if (GetWindowRect(hwnd, out RECT wr)
            && DwmGetWindowAttributeRect(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, out RECT fb, Marshal.SizeOf<RECT>()) == 0)
        {
            int l = Math.Max(0, fb.Left - wr.Left);
            int t = Math.Max(0, fb.Top - wr.Top);
            int r = Math.Max(0, wr.Right - fb.Right);
            int b = Math.Max(0, wr.Bottom - fb.Bottom);
            return (l, t, r, b);
        }
        return (0, 0, 0, 0);
    }
}
