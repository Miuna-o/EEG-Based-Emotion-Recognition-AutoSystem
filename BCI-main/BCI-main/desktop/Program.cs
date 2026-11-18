using System.Security.Cryptography;
using System.Text;
using System.Runtime.InteropServices;

namespace Xinlan.Desktop;

internal static class Program
{
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr handle);
    [STAThread]
    private static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            var root = FindProject();
            var identity = root.ToUpperInvariant() + "|" + Environment.GetEnvironmentVariable("XINLAN_STORAGE_DIR");
            var key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(identity)))[..24];
            using var mutex = new Mutex(true, @"Local\Xinlan.App." + key, out bool first);
            using var activate = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\Xinlan.Activate." + key);
            if (!first) { activate.Set(); return; }
            using var window = new MainWindow(root);
            // 提前创建句柄，避免重复启动时激活事件发生在 Shown 之前。
            _ = window.Handle;
            var listener = ThreadPool.RegisterWaitForSingleObject(activate, (_, _) =>
            {
                if (!window.IsDisposed)
                {
                    try { window.BeginInvoke(() => {
                        if (window.WindowState == FormWindowState.Minimized) window.WindowState = FormWindowState.Normal;
                        window.Show(); window.Activate(); SetForegroundWindow(window.Handle);
                    }); } catch (InvalidOperationException) { }
                }
            }, null, Timeout.Infinite, false);
            try { Application.Run(window); }
            finally { listener.Unregister(null); mutex.ReleaseMutex(); }
        }
        catch (Exception error)
        {
            MessageBox.Show("心澜未能启动。\n\n" + error.Message + "\n\n请运行工程中的“诊断心澜.bat”。",
                            "心澜 · 启动提示", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static string FindProject()
    {
        for (DirectoryInfo? directory = new(AppContext.BaseDirectory); directory != null; directory = directory.Parent)
            if (File.Exists(Path.Combine(directory.FullName, "config", "xinlan.json")) &&
                File.Exists(Path.Combine(directory.FullName, "scripts", "desktop_service.py"))) return directory.FullName;
        throw new DirectoryNotFoundException("请保留完整应用目录，不要单独移动心澜.exe。可将快捷方式放到任意位置。");
    }
}
