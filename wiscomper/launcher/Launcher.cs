using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("万象世界启动器")]
[assembly: AssemblyProduct("Wisdom Perspective")]
[assembly: AssemblyDescription("启动同目录的 Start.ps1；网站更新无需重新编译启动器。")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

internal static class Launcher
{
    private static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;
    private static readonly object LogLock = new object();
    private static StreamWriter Log;
    private static string LogPath;
    private static int LoggedCharacters;
    private const int LogLimit = 262144;

    private sealed class Options
    {
        public bool NoBrowser;
        public int Port;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        bool quiet = Array.Exists(args, a => a == "--quiet");
        int result = 1;
        try
        {
            OpenLog();
            Options options = Parse(args);
            if (quiet)
            {
                result = Start(options);
            }
            else
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                using (var splash = MakeSplash())
                {
                    splash.Shown += async (sender, e) =>
                    {
                        try { result = await Task.Run(() => Start(options)); }
                        catch (Exception ex) { WriteLog("ERROR: " + ex.Message); result = 1; }
                        splash.Hide();
                        if (result != 0) ShowFailure();
                        splash.Close();
                    };
                    Application.Run(splash);
                }
            }
        }
        catch (Exception ex)
        {
            WriteLog("ERROR: " + ex.Message);
            if (!quiet) ShowFailure(ex.Message);
            result = 1;
        }
        finally
        {
            lock (LogLock) { if (Log != null) { Log.Dispose(); Log = null; } }
        }
        return result;
    }

    private static Options Parse(string[] args)
    {
        var options = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--quiet": break;
                case "--no-browser": options.NoBrowser = true; break;
                case "--port":
                    if (++i >= args.Length || !int.TryParse(args[i], out options.Port)
                        || options.Port < 1024 || options.Port > 65535)
                        throw new ArgumentException("--port 需要填写 1024–65535 之间的端口。使用默认端口时请省略此参数。");
                    break;
                default: throw new ArgumentException("未知启动参数。支持：--no-browser、--quiet、--port 端口号。");
            }
        }
        return options;
    }

    private static int Start(Options options)
    {
        string script = Path.Combine(Root, "Start.ps1");
        if (!File.Exists(script))
            throw new FileNotFoundException("找不到同目录的 Start.ps1。请把 EXE 保留在完整项目目录中，桌面上使用快捷方式。");
        string powershell = FindPowerShell();
        var info = new ProcessStartInfo
        {
            FileName = powershell,
            Arguments = "-NoLogo -NoProfile -NonInteractive -File " + QuoteArgument(script)
                + (options.NoBrowser ? " -NoBrowser" : "")
                + (options.Port > 0 ? " -Port " + options.Port : ""),
            WorkingDirectory = Root,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        };
        info.EnvironmentVariables["NO_COLOR"] = "1";
        info.EnvironmentVariables["TERM"] = "dumb";
        WriteLog("Starting the adjacent Start.ps1.");
        using (var process = new Process { StartInfo = info })
        {
            var outputClosed = new TaskCompletionSource<bool>();
            var errorClosed = new TaskCompletionSource<bool>();
            process.OutputDataReceived += (sender, e) =>
            {
                if (e.Data == null) outputClosed.TrySetResult(true);
                else WriteLog(e.Data);
            };
            process.ErrorDataReceived += (sender, e) =>
            {
                if (e.Data == null) errorClosed.TrySetResult(true);
                else WriteLog("STDERR: " + e.Data);
            };
            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            // Start.ps1 owns service health, startup timeout, locking and cleanup.
            // Allow its 35-second lock and up to 120-second startup to complete.
            if (!process.WaitForExit(240000))
            {
                WriteLog("Startup did not return within 4 minutes. Inspect service logs before trying again. No process was terminated.");
                // Closing this launcher never terminates the independently running service.
                process.CancelOutputRead();
                process.CancelErrorRead();
                return 1;
            }
            // Detached server descendants may inherit a pipe handle even after
            // pwsh exits. An unbounded WaitForExit() would keep the splash open.
            if (!Task.WaitAll(new Task[] { outputClosed.Task, errorClosed.Task }, 2000))
            {
                process.CancelOutputRead();
                process.CancelErrorRead();
            }
            WriteLog("Startup exit code: " + process.ExitCode);
            return process.ExitCode == 0 ? 0 : 1;
        }
    }

    private static string FindPowerShell()
    {
        string config = Path.Combine(Root, "launcher.ini");
        if (File.Exists(config))
        {
            bool inSection = false;
            foreach (string original in File.ReadAllLines(config, Encoding.UTF8))
            {
                string line = original.Trim();
                if (line.Length == 0 || line.StartsWith(";") || line.StartsWith("#")) continue;
                if (line.StartsWith("[")) { inSection = line.Equals("[launcher]", StringComparison.OrdinalIgnoreCase); continue; }
                int equals = line.IndexOf('=');
                if (!inSection || equals < 0 || !line.Substring(0, equals).Trim().Equals("PowerShellPath", StringComparison.OrdinalIgnoreCase)) continue;
                string value = line.Substring(equals + 1).Trim().Trim('"');
                if (value.Length == 0) break;
                value = Environment.ExpandEnvironmentVariables(value);
                value = Path.GetFullPath(Path.IsPathRooted(value) ? value : Path.Combine(Root, value));
                if (!IsPowerShell7(value))
                    throw new FileNotFoundException("launcher.ini 的 PowerShellPath 无效，请填写 PowerShell 7 或更新版本的 pwsh.exe 路径，或留空自动查找。");
                return value;
            }
        }

        var candidates = new List<string>();
        foreach (string name in new[] { "ProgramW6432", "ProgramFiles" })
        {
            string folder = Environment.GetEnvironmentVariable(name);
            if (!string.IsNullOrWhiteSpace(folder)) candidates.Add(Path.Combine(folder, "PowerShell", "7", "pwsh.exe"));
        }
        candidates.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Microsoft", "PowerShell", "7", "pwsh.exe"));
        foreach (string directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            string folder = directory.Trim().Trim('"');
            // Do not resolve bare/current-directory entries as executable search paths.
            if (folder.Length == 0 || !Path.IsPathRooted(folder)) continue;
            try { candidates.Add(Path.Combine(folder, "pwsh.exe")); }
            catch (ArgumentException) { }
        }
        // The user's existing Codex runtime also works when Explorer has an older PATH.
        candidates.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "native", "powershell", "pwsh.exe"));
        foreach (string path in candidates) if (IsPowerShell7(path)) return path;
        throw new FileNotFoundException("没有找到 PowerShell 7。安装后重试，或在 launcher.ini 中填写现有 pwsh.exe 的路径。");
    }

    private static bool IsPowerShell7(string path)
    {
        if (!File.Exists(path) || !Path.GetFileName(path).Equals("pwsh.exe", StringComparison.OrdinalIgnoreCase)) return false;
        try { return FileVersionInfo.GetVersionInfo(path).FileMajorPart >= 7; }
        catch (IOException) { return false; }
        catch (UnauthorizedAccessException) { return false; }
    }

    // Windows argv quoting, not PowerShell source interpolation. -File keeps
    // apostrophes, ampersands and dollar signs in the installation path literal.
    private static string QuoteArgument(string value)
    {
        var output = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') output.Append('\\', slashes * 2 + 1).Append(c);
            else output.Append('\\', slashes).Append(c);
            slashes = 0;
        }
        return output.Append('\\', slashes * 2).Append('"').ToString();
    }

    private static void OpenLog()
    {
        string filename = "launcher-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".log";
        string[] directories = {
            Path.Combine(Root, "data", "service", "logs"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WisdomPerspective", "launcher-logs")
        };
        foreach (string directory in directories)
        {
            try
            {
                Directory.CreateDirectory(directory);
                LogPath = Path.Combine(directory, filename);
                Log = new StreamWriter(new FileStream(LogPath, FileMode.CreateNew, FileAccess.Write, FileShare.Read), new UTF8Encoding(false)) { AutoFlush = true };
                WriteLog("Wisdom Perspective launcher / " + DateTime.UtcNow.ToString("o"));
                return;
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        LogPath = null;
        throw new IOException("无法创建启动日志，请确认项目目录或当前用户目录可写。");
    }

    private static void WriteLog(string message)
    {
        lock (LogLock)
        {
            if (Log == null || LoggedCharacters >= LogLimit) return;
            string text = message.Length > 8192 ? message.Substring(0, 8192) + " [truncated]" : message;
            try { Log.WriteLine(text); LoggedCharacters += text.Length + 2; }
            catch (IOException) { }
            catch (ObjectDisposedException) { }
        }
    }

    private static Form MakeSplash()
    {
        var form = new Form
        {
            Text = "万象世界 · Wisdom Perspective",
            ClientSize = new Size(420, 180),
            StartPosition = FormStartPosition.CenterScreen,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            ControlBox = false,
            ShowInTaskbar = true,
            BackColor = Color.FromArgb(248, 250, 255),
            AutoScaleMode = AutoScaleMode.Dpi,
            Font = new Font("Microsoft YaHei UI", 9F)
        };
        form.Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        var logo = new PictureBox { Location = new Point(27, 24), Size = new Size(68, 68), SizeMode = PictureBoxSizeMode.Zoom };
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("wisdom-logo.png"))
        using (Image source = Image.FromStream(stream)) logo.Image = new Bitmap(source);
        form.Controls.Add(logo);
        form.Controls.Add(new Label { Text = "万象世界", Location = new Point(110, 28), AutoSize = true,
            Font = new Font("Microsoft YaHei UI", 18F, FontStyle.Bold), ForeColor = Color.FromArgb(38, 53, 88) });
        form.Controls.Add(new Label { Text = "Wisdom Perspective", Location = new Point(113, 65), AutoSize = true, ForeColor = Color.FromArgb(103, 115, 147) });
        form.Controls.Add(new Label { Text = "正在准备你的可视化世界…", Location = new Point(30, 112), AutoSize = true, ForeColor = Color.FromArgb(82, 98, 132) });
        form.Controls.Add(new ProgressBar { Location = new Point(30, 143), Size = new Size(360, 6), Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 28 });
        form.FormClosed += (sender, e) => { if (logo.Image != null) logo.Image.Dispose(); };
        return form;
    }

    private static void ShowFailure(string reason = null)
    {
        string message = reason ?? "网站未能完成启动。请先查看日志中的具体原因；项目环境、端口或启动脚本可能需要检查。";
        if (LogPath != null) message += "\n\n启动日志：\n" + LogPath;
        MessageBox.Show(message, "万象世界 · 启动未完成", MessageBoxButtons.OK, MessageBoxIcon.Warning);
    }
}
