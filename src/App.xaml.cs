using System.Windows;

namespace WindowMerger;

public partial class App : Application
{
    private void OnStartup(object sender, StartupEventArgs e)
    {
        // 命令行：WindowMerger.exe [--left 左进程名|左PID] [--right 右进程名|右PID] 或位置参数 [左] [右]
        // 纯数字参数按 PID 匹配（脚本 Start-Process -PassThru 可直接拿到目标进程 PID）
        var (left, right) = ParseArgs(e.Args);
        var host = new HostWindow(ConfigStore.Load(), left, right);
        MainWindow = host;
        host.Show();
    }

    /// <summary>命名参数 --left/-l、--right/-r；其余位置参数按 [左] [右] 兜底。</summary>
    private static (string? Left, string? Right) ParseArgs(string[] args)
    {
        string? left = null, right = null;
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            if ((a is "--left" or "-l" or "/left" or "/l") && i + 1 < args.Length)
            {
                left = args[++i];
            }
            else if ((a is "--right" or "-r" or "/right" or "/r") && i + 1 < args.Length)
            {
                right = args[++i];
            }
            else if (left is null)
            {
                left = a;
            }
            else if (right is null)
            {
                right = a;
            }
        }
        return (left, right);
    }
}
