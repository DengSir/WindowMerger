using System.Windows;

namespace WindowMerger;

public partial class App : Application
{
    private void OnStartup(object sender, StartupEventArgs e)
    {
        // 命令行：WindowMerger.exe [--left 左进程名|左PID] [--right 右进程名|右PID]
        //         [--left-exe 左exe完整路径] [--right-exe 右exe完整路径] 或位置参数 [左] [右]
        // 纯数字参数按 PID 匹配（脚本 Start-Process -PassThru 可直接拿到目标进程 PID）；
        // exe 路径用于目标未运行时自动拉起（快捷方式复现组合用）
        var (left, right, leftExe, rightExe) = ParseArgs(e.Args);
        var host = new HostWindow(ConfigStore.Load(), left, right, leftExe, rightExe);
        MainWindow = host;
        host.Show();
    }

    /// <summary>命名参数 --left/-l、--right/-r、--left-exe、--right-exe；其余位置参数按 [左] [右] 兜底。</summary>
    private static (string? Left, string? Right, string? LeftExe, string? RightExe) ParseArgs(string[] args)
    {
        string? left = null, right = null, leftExe = null, rightExe = null;
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
            else if ((a is "--left-exe" or "/left-exe") && i + 1 < args.Length)
            {
                leftExe = args[++i];
            }
            else if ((a is "--right-exe" or "/right-exe") && i + 1 < args.Length)
            {
                rightExe = args[++i];
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
        return (left, right, leftExe, rightExe);
    }
}
