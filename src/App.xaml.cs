using System.Windows;

namespace WindowMerger;

public partial class App : Application
{
    private void OnStartup(object sender, StartupEventArgs e)
    {
        var host = new HostWindow(ConfigStore.Load());
        MainWindow = host;
        host.Show();
    }
}
