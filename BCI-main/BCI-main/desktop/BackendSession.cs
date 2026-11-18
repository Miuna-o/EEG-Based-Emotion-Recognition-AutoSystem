using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace Xinlan.Desktop;

internal sealed class BackendSession : IDisposable
{
    private Process? supervisor;
    private Task<string>? errors;
    public Uri Address { get; private set; } = null!;
    public string ProfileDirectory { get; private set; } = "";

    public async Task StartAsync(string root)
    {
        var python = Path.Combine(root, ".runtime", "Scripts", "python.exe");
        if (!File.Exists(python)) throw new FileNotFoundException("缺少本地运行环境，请先运行安装心澜.bat。", python);
        if (!File.Exists(Path.Combine(root, "frontend", "dist", "index.html")))
            throw new FileNotFoundException("应用界面尚未构建，请运行 scripts/build-desktop.ps1。");
        var info = new ProcessStartInfo(python) {
            WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var arg in new[] { "-B", "-X", "utf8", "scripts/desktop_service.py" }) info.ArgumentList.Add(arg);
        supervisor = Process.Start(info) ?? throw new InvalidOperationException("无法创建本地服务进程。");
        errors = supervisor.StandardError.ReadToEndAsync();
        var line = await supervisor.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(45));
        if (line == null) throw new InvalidOperationException("本地服务未能启动。\n" + await errors);
        using var ready = JsonDocument.Parse(line);
        if (ready.RootElement.GetProperty("status").GetString() != "ready")
            throw new InvalidOperationException(ready.RootElement.GetProperty("message").GetString());
        Address = new Uri(ready.RootElement.GetProperty("url").GetString()!);
        if (!Address.IsLoopback || Address.Scheme != "http") throw new InvalidOperationException("本地服务返回了无效地址。");
        ProfileDirectory = ready.RootElement.GetProperty("profile_dir").GetString()!;
    }

    public async Task StopAsync()
    {
        if (supervisor == null) return;
        if (!supervisor.HasExited)
        {
            // 关闭管道同时覆盖正常退出和初始化尚未完成的情况。
            supervisor.StandardInput.Close();
            await supervisor.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(25));
        }
        if (supervisor.ExitCode != 0 && errors != null)
            throw new InvalidOperationException("本地服务退出时报告异常。\n" + await errors);
    }

    public void Dispose()
    {
        if (supervisor == null) return;
        try { supervisor.StandardInput.Close(); } catch (InvalidOperationException) { }
        supervisor.Dispose();
    }
}
