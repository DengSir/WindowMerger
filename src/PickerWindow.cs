using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;

namespace WindowMerger;

public enum AttachSide
{
    Left,
    Right,
}

public sealed class PickerWindow : Window
{
    private readonly IntPtr _excludeHwnd;
    private readonly ObservableCollection<WindowCandidate> _items = new();
    private ListView _list = null!;
    private TextBox _filter = null!;

    public WindowCandidate? Result { get; private set; }

    public PickerWindow(AttachSide side, IntPtr excludeHwnd)
    {
        _excludeHwnd = excludeHwnd;

        Title = side == AttachSide.Left ? "选择吸附到【左侧】的窗口" : "选择吸附到【右侧】的窗口";
        Width = 640;
        Height = 480;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        ShowInTaskbar = false;
        ResizeMode = ResizeMode.CanResize;

        var grid = new Grid { Margin = new Thickness(10) };
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        _filter = new TextBox
        {
            Margin = new Thickness(0, 0, 0, 8),
            FontSize = 13,
        };
        _filter.TextChanged += (_, _) => ApplyFilter();
        Grid.SetRow(_filter, 0);
        grid.Children.Add(_filter);

        var view = new GridView
        {
            Columns =
            {
                new GridViewColumn { Header = "标题", DisplayMemberBinding = new Binding(nameof(WindowCandidate.Title)), Width = 300 },
                new GridViewColumn { Header = "进程", DisplayMemberBinding = new Binding(nameof(WindowCandidate.ProcessName)), Width = 100 },
                new GridViewColumn { Header = "PID", DisplayMemberBinding = new Binding(nameof(WindowCandidate.Pid)), Width = 60 },
                new GridViewColumn { Header = "类名", DisplayMemberBinding = new Binding(nameof(WindowCandidate.ClassName)), Width = 140 },
            },
        };
        _list = new ListView
        {
            View = view,
            ItemsSource = _items,
        };
        _list.MouseDoubleClick += (_, _) => Confirm();
        Grid.SetRow(_list, 1);
        grid.Children.Add(_list);

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 8, 0, 0),
        };
        var refresh = new Button { Content = "刷新", Width = 80, Margin = new Thickness(0, 0, 8, 0) };
        refresh.Click += (_, _) => Reload();
        var ok = new Button { Content = "吸附", Width = 80, Margin = new Thickness(0, 0, 8, 0), IsDefault = true };
        ok.Click += (_, _) => Confirm();
        var cancel = new Button { Content = "取消", Width = 80, IsCancel = true };
        buttons.Children.Add(refresh);
        buttons.Children.Add(ok);
        buttons.Children.Add(cancel);
        Grid.SetRow(buttons, 2);
        grid.Children.Add(buttons);

        Content = grid;
        Loaded += (_, _) => Reload();
    }

    private void Reload()
    {
        _items.Clear();
        foreach (var c in WindowLocator.GetCandidates(_excludeHwnd)) _items.Add(c);
        ApplyFilter();
    }

    private void ApplyFilter()
    {
        string q = _filter.Text.Trim();
        CollectionViewSource.GetDefaultView(_items).Filter = o => o is WindowCandidate c
            && (q.Length == 0
                || c.Title.Contains(q, StringComparison.OrdinalIgnoreCase)
                || c.ProcessName.Contains(q, StringComparison.OrdinalIgnoreCase));
    }

    private void Confirm()
    {
        if (_list.SelectedItem is WindowCandidate c)
        {
            Result = c;
            DialogResult = true;
        }
    }
}
