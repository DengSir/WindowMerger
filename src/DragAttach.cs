using System.Windows.Threading;

namespace WindowMerger;

/// <summary>
/// 全局窗口事件编排，两路职责：
/// 拖入吸附——监听任意窗口的移动（EVENT_SYSTEM_MOVESIZE / MOVESIZEEND），
///   光标落在宿主左/右洞内时高亮目标格，松手后吸附进该格——以光标为准，
///   窗口中心在洞内但光标在洞外不吸附（拖标题条时窗口体悬在洞上不算抓取）；
/// 前台联动——监听 EVENT_SYSTEM_FOREGROUND，吸附子窗口成为前台时把整个
///   合并单元升到普通窗口之上（见 HostWindow.OnChildActivated）。
/// </summary>
internal sealed class DragAttach : IDisposable
{
    private readonly HostWindow _host;
    private readonly Native.WinEventProc _proc; // 保活，防止回调被 GC
    private IntPtr _hook;
    private IntPtr _hookFg;
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
        _hookFg = Native.SetWinEventHook(
            Native.EVENT_SYSTEM_FOREGROUND, Native.EVENT_SYSTEM_FOREGROUND,
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

        if (@event == Native.EVENT_SYSTEM_FOREGROUND)
        {
            // 子窗口成为前台（用户点格子穿透激活/程序自激活）：整个合并单元随之升到
            // 普通窗口之上，对齐普通窗口"点哪整窗到前"的行为
            if (_host.IsAttachedChild(hwnd)) _host.OnChildActivated(hwnd);
            return;
        }
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
            var side = HitTestSlot(hwnd);
            _host.SetDragHighlight(null);
            if (side is not null)
            {
                _host.TryAttach(side.Value, hwnd);
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

    private AttachSide? HitTestSlot(IntPtr hwnd)
    {
        // 已吸附子窗口拖动也亮框（归位语义），其余窗口走常规吸附判定
        if (!_host.IsAttachable(hwnd) && !_host.IsAttachedChild(hwnd)) return null;
        // 光标位置为准（MOVESIZEEND 时即松手点），物理设备像素与窗口矩形同坐标系
        if (!Native.GetCursorPos(out var p)) return null;
        var side = _host.HitTestPaneAt(p.X, p.Y);
        if (side is null) return null;
        // 光标处宿主上层有别的窗口（如另一实例的宿主）：用户看到的不是我们的格子，
        // 不亮框也不吸附——同一可见层只有一个实例能抓到
        if (_host.IsCoveredAtCursor(hwnd)) return null;
        return _host.IsDropAllowed(hwnd, side.Value) ? side : null; // 不允许就不显示高亮
    }

    public void Dispose()
    {
        _poll.Stop();
        if (_hook != IntPtr.Zero)
        {
            Native.UnhookWinEvent(_hook);
            _hook = IntPtr.Zero;
        }
        if (_hookFg != IntPtr.Zero)
        {
            Native.UnhookWinEvent(_hookFg);
            _hookFg = IntPtr.Zero;
        }
    }
}
