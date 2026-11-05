using System.Windows.Threading;

namespace WindowMerger;

/// <summary>
/// 拖入吸附：全局监听任意窗口的移动（EVENT_SYSTEM_MOVESIZE / MOVESIZEEND），
/// 光标落在宿主左/右洞内时高亮目标格，松手后吸附进该格——以光标为准，
/// 窗口中心在洞内但光标在洞外不吸附（拖标题条时窗口体悬在洞上不算抓取）。
/// </summary>
internal sealed class DragAttach : IDisposable
{
    private readonly HostWindow _host;
    private readonly Native.WinEventProc _proc; // 保活，防止回调被 GC
    private IntPtr _hook;
    private IntPtr _dragHwnd;
    private readonly DispatcherTimer _poll;

    public DragAttach(HostWindow host)
    {
        _host = host;
        _proc = OnWinEvent;
        _hook = Native.SetWinEventHook(
            Native.EVENT_SYSTEM_MOVESIZE, Native.EVENT_SYSTEM_MOVESIZEEND,
            IntPtr.Zero, _proc, 0, 0,
            Native.WINEVENT_OUTOFCONTEXT | Native.WINEVENT_SKIPOWNPROCESS);
        _poll = new DispatcherTimer(DispatcherPriority.Input)
        {
            Interval = TimeSpan.FromMilliseconds(50),
        };
        _poll.Tick += (_, _) => UpdateHighlight();
    }

    public bool IsBusy => _dragHwnd != IntPtr.Zero;

    private void OnWinEvent(IntPtr hook, uint @event, IntPtr hwnd, int idObject, int idChild, uint thread, uint time)
    {
        if (idObject != Native.OBJID_WINDOW || hwnd == IntPtr.Zero) return;

        if (@event == Native.EVENT_SYSTEM_MOVESIZE)
        {
            _dragHwnd = hwnd;
            UpdateHighlight();
            _poll.Start();
        }
        else if (@event == Native.EVENT_SYSTEM_MOVESIZEEND && _dragHwnd == hwnd)
        {
            _poll.Stop();
            _dragHwnd = IntPtr.Zero;
            int slot = HitTestSlot(hwnd);
            _host.SetDragHighlight(-1);
            if (slot >= 0)
            {
                _host.TryAttach(slot == 0 ? AttachSide.Left : AttachSide.Right, hwnd);
            }
        }
    }

    private void UpdateHighlight()
    {
        if (_dragHwnd == IntPtr.Zero)
        {
            _poll.Stop();
            return;
        }
        _host.SetDragHighlight(HitTestSlot(_dragHwnd));
    }

    private int HitTestSlot(IntPtr hwnd)
    {
        // 已吸附子窗口拖动也亮框（归位语义），其余窗口走常规吸附判定
        if (!_host.IsAttachable(hwnd) && !_host.IsAttachedChild(hwnd)) return -1;
        // 光标位置为准（MOVESIZEEND 时即松手点），物理设备像素与窗口矩形同坐标系
        if (!Native.GetCursorPos(out var p)) return -1;
        int slot = _host.HitTestPaneAt(p.X, p.Y);
        if (slot < 0) return -1;
        return _host.IsDropAllowed(hwnd, slot) ? slot : -1; // 不允许就不显示高亮
    }

    public void Dispose()
    {
        _poll.Stop();
        if (_hook != IntPtr.Zero)
        {
            Native.UnhookWinEvent(_hook);
            _hook = IntPtr.Zero;
        }
    }
}
