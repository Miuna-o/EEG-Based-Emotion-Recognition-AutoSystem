using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Xinlan.Desktop;

internal sealed class MainWindow : Form
{
    private readonly BackendSession backend = new();
    private readonly string root;
    private readonly Label loading = new() {
        Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter,
        Text = "心澜\n\n正在准备本地工作台…", ForeColor = Color.FromArgb(15, 118, 110),
        Font = new Font("Microsoft YaHei UI", 18), BackColor = Color.FromArgb(247, 250, 249)
    };
    private readonly WebView2 browser = new() { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.FromArgb(247, 250, 249) };
    private readonly List<Form> previews = [];
    private bool shuttingDown;
    private bool mayClose;
    private CoreWebView2Environment? environment;

    public MainWindow(string root)
    {
        this.root = root;
        Text = "心澜";
        Icon = new Icon(Path.Combine(AppContext.BaseDirectory, "xinlan.ico"));
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(1440, 900);
        MinimumSize = new Size(1024, 720);
        var area = Screen.PrimaryScreen!.WorkingArea;
        Size = new Size(Math.Min(Width, area.Width - 32), Math.Min(Height, area.Height - 32));
        Controls.Add(browser); Controls.Add(loading);
        Shown += async (_, _) => await InitializeAsync();
        FormClosing += ClosingAsync;
        FormClosed += (_, _) => { backend.Dispose(); };
    }

    private async Task InitializeAsync()
    {
        try
        {
            await backend.StartAsync(root);
            if (shuttingDown) return;
            // 使用系统 WebView2 内核；网页设计和所有资源仍来自本机。
            environment = await CoreWebView2Environment.CreateAsync(userDataFolder: backend.ProfileDirectory);
            await browser.EnsureCoreWebView2Async(environment);
            if (shuttingDown) return;
            ConfigureBrowser(browser, this);
            browser.CoreWebView2.NavigationCompleted += (_, args) => {
                if (shuttingDown) return;
                if (args.IsSuccess) loading.Visible = false;
                else { loading.Visible = true; loading.Text = "本地界面加载失败\n\n请关闭后重新打开心澜，或运行诊断心澜.bat。"; }
            };
            browser.Source = backend.Address;
        }
        catch (Exception error)
        {
            if (shuttingDown) return;
            loading.Text = "心澜暂时无法启动\n\n" + error.Message;
            MessageBox.Show(this, error.Message + "\n\n请运行工程内的诊断心澜.bat。", "心澜 · 启动提示",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            Close();
        }
    }

    private bool Allowed(string address)
    {
        if (address == "about:blank") return true;
        if (address.StartsWith("blob:", StringComparison.OrdinalIgnoreCase)) address = address[5..];
        return Uri.TryCreate(address, UriKind.Absolute, out var target) &&
               target.Scheme == backend.Address.Scheme && target.Host == backend.Address.Host && target.Port == backend.Address.Port;
    }

    private void ConfigureBrowser(WebView2 view, Form owner)
    {
        var core = view.CoreWebView2;
        var downloadStaging = Path.Combine(backend.ProfileDirectory, "downloads");
        Directory.CreateDirectory(downloadStaging);
        core.Profile.DefaultDownloadFolderPath = downloadStaging;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.AreHostObjectsAllowed = false;
        core.Settings.IsWebMessageEnabled = false;
        core.Settings.IsGeneralAutofillEnabled = false;
        core.Settings.IsPasswordAutosaveEnabled = false;
        core.NavigationStarting += (_, args) => { if (!Allowed(args.Uri)) args.Cancel = true; };
        core.PermissionRequested += (_, args) => args.State = CoreWebView2PermissionState.Deny;
        core.DownloadStarting += (_, args) => {
            void LogDownload(string message) {
                try { File.AppendAllText(Path.Combine(backend.ProfileDirectory, "desktop-events.log"), $"{DateTimeOffset.Now} {message}\n"); }
                catch (IOException) { }
            }
            LogDownload($"download allowed={Allowed(args.DownloadOperation.Uri)}");
            args.DownloadOperation.StateChanged += (_, _) => LogDownload($"download state={args.DownloadOperation.State} reason={args.DownloadOperation.InterruptReason}");
            if (!Allowed(args.DownloadOperation.Uri)) { args.Cancel = true; return; }
            args.Handled = true;
            var deferral = args.GetDeferral();
            // WebView2 回调内不进入模态消息循环；退出回调后再显示系统保存框。
            owner.BeginInvoke(() => {
                using (deferral)
                {
                    if (shuttingDown || owner.IsDisposed) { args.Cancel = true; return; }
                    using var dialog = new SaveFileDialog {
                        Title = "保存心澜文件", FileName = Path.GetFileName(args.ResultFilePath),
                        InitialDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads"),
                        Filter = "所有文件 (*.*)|*.*", OverwritePrompt = true, RestoreDirectory = true
                    };
                    try {
                        var result = dialog.ShowDialog(owner);
                        LogDownload($"save dialog result={result}");
                        if (result != DialogResult.OK) { args.Cancel = true; return; }
                        args.ResultFilePath = dialog.FileName;
                    } catch (Exception error) {
                        args.Cancel = true;
                        MessageBox.Show(owner, "无法打开保存对话框：" + error.Message, "心澜 · 保存提示");
                    }
                }
            });
        };
        core.NewWindowRequested += async (_, args) => {
            args.Handled = true;
            if (!Allowed(args.Uri) || shuttingDown) return;
            using var deferral = args.GetDeferral();
            var preview = new Form { Text = "心澜 · 报告预览", Icon = Icon,
                Size = new Size(1000, 820), StartPosition = FormStartPosition.CenterParent };
            var previewBrowser = new WebView2 { Dock = DockStyle.Fill };
            preview.Controls.Add(previewBrowser);
            previews.Add(preview);
            preview.FormClosed += (_, _) => previews.Remove(preview);
            try {
                preview.Show(this);
                await previewBrowser.EnsureCoreWebView2Async(environment);
                ConfigureBrowser(previewBrowser, preview);
                // 报告预览不依赖 opener；显式导航自己的 WebView，避免空白弹窗接管竞态。
                previewBrowser.CoreWebView2.Navigate(args.Uri);
            } catch (Exception error) {
                preview.Close();
                if (!shuttingDown) MessageBox.Show(this, error.Message, "心澜 · 预览提示");
            }
        };
        core.ProcessFailed += (_, failure) => {
            if (!shuttingDown && !owner.IsDisposed)
            {
                var diagnostic = $"{failure.ProcessFailedKind} / {failure.Reason} / {failure.ExitCode}";
                try { File.AppendAllText(Path.Combine(backend.ProfileDirectory, "desktop-errors.log"), DateTimeOffset.Now + " " + diagnostic + Environment.NewLine); } catch (IOException) { }
                // GPU/工具进程异常由 WebView2 自行恢复，阻塞消息框会阻断恢复流程。
                if (failure.ProcessFailedKind != CoreWebView2ProcessFailedKind.BrowserProcessExited &&
                    failure.ProcessFailedKind != CoreWebView2ProcessFailedKind.RenderProcessExited) return;
                owner.BeginInvoke(() => {
                    if (!shuttingDown && !owner.IsDisposed)
                        MessageBox.Show(owner, "应用显示组件已停止。请关闭后重新打开心澜；已保存的记录仍保存在本机。\n\n错误信息：" + diagnostic, "心澜 · 显示提示");
                });
            }
        };
    }

    private async void ClosingAsync(object? sender, FormClosingEventArgs args)
    {
        if (mayClose) return;
        args.Cancel = true;
        if (shuttingDown) return;
        shuttingDown = true;
        loading.Visible = true; loading.BringToFront(); loading.Text = "正在关闭心澜…";
        foreach (var preview in previews.ToArray()) preview.Close();
        browser.Dispose();
        try { await backend.StopAsync(); }
        catch (Exception error) {
            MessageBox.Show(this, "服务尚未正常退出，可运行停止心澜.bat 再次检查。\n\n" + error.Message,
                            "心澜 · 退出提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        mayClose = true; Close();
    }
}
