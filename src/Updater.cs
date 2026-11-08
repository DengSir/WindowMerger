using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace WindowMerger;

/// <summary>
/// GitHub Release 自动更新：检查 releases/latest → 下载 zip → 解出 exe → 自替换 → 重启。
/// 单文件 exe 运行中不可覆写但可改名（publish.py 同款实证），换装时序（宿主 Closing 清理完
/// 成后调用 InstallAndRestart）：旧 exe 改名 .old → 新 exe 落位原路径 → 拉起新实例。
/// 测试钩子：环境变量 WM_UPDATE_API 覆盖 releases/latest 地址（本地 HTTP 服务模拟 GitHub，
/// asset 下载地址直接取 JSON 里的 browser_download_url，无需第二处覆盖）。
/// </summary>
internal static class Updater
{
    public const string RepoApi = "https://api.github.com/repos/DengSir/WindowMerger/releases/latest";

    /// <summary>更新包里 exe 的固定 entry 名（tools/ci/release.py stage 约定，不随版本改名）。</summary>
    private const string ZipEntryName = "WindowMerger.exe";

    private static readonly HttpClient Http = CreateClient();

    private static HttpClient CreateClient()
    {
        var http = new HttpClient { Timeout = TimeSpan.FromSeconds(30) }; // 检查/拿下载响应头；下载本体走流不受它限制
        // GitHub API 必须带 User-Agent，否则 403
        http.DefaultRequestHeaders.UserAgent.ParseAdd($"WindowMerger/{CurrentDisplayVersion()}");
        return http;
    }

    public sealed record UpdateInfo(string Version, string ZipUrl);

    /// <summary>检查结果：Update=null 且 NoRelease=false = 已是最新；NoRelease=true = 仓库还没有正式 Release。</summary>
    public sealed record UpdateCheck(UpdateInfo? Update, bool NoRelease);

    // ---------- 版本 ----------

    /// <summary>显示版本 = InformationalVersion（CI 发版写 tag 版本；本地构建 = csproj Version，可能带 +hash 段）。
    /// 单文件发布下 Assembly.Location 为空串，不能走 FileVersionInfo.GetVersionInfo(Assembly.Location)。</summary>
    public static string CurrentDisplayVersion()
    {
        string? v = Assembly.GetExecutingAssembly()
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
        if (string.IsNullOrEmpty(v)) return "0.0.0";
        int plus = v.IndexOf('+');
        return plus >= 0 ? v[..plus] : v;
    }

    /// <summary>数字前缀解析（与 publish.py / tools/ci/release.py 同款规则）：v 前缀、预发布段（-alpha.1）
    /// 与 hash 段（a242d884、+sha）都不参与比较。解析失败返回 null——无法理解的版本绝不触发更新。</summary>
    public static Version? ParseVersion(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        Match m = Regex.Match(raw.Trim(), @"^v?(\d+(?:\.\d+){0,3})");
        return m.Success && Version.TryParse(m.Groups[1].Value, out var v) ? v : null;
    }

    /// <summary>远端版本是否比当前新。</summary>
    public static bool IsNewer(string remote)
        => ParseVersion(remote) is { } r && r > ParseVersion(CurrentDisplayVersion());

    private static string StripV(string tag) => tag.StartsWith('v') ? tag[1..] : tag;

    // ---------- 检查 ----------

    /// <summary>查最新稳定版（releases/latest 天然排除 draft/prerelease）。网络/解析异常上抛给调用方报因。</summary>
    public static async Task<UpdateCheck> CheckLatestAsync(CancellationToken ct = default)
    {
        string url = Environment.GetEnvironmentVariable("WM_UPDATE_API") is { Length: > 0 } api ? api : RepoApi;
        using var resp = await Http.GetAsync(url, ct);
        if (resp.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            return new UpdateCheck(null, NoRelease: true);
        }
        resp.EnsureSuccessStatusCode();

        await using var stream = await resp.Content.ReadAsStreamAsync(ct);
        using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: ct);
        var root = doc.RootElement;

        string tag = root.TryGetProperty("tag_name", out var t) ? t.GetString() ?? "" : "";
        if (!IsNewer(tag))
        {
            return new UpdateCheck(null, NoRelease: false);
        }

        // asset 按发布物后缀匹配（WindowMerger-<版本>-win-x64.zip），不硬编码版本号
        if (root.TryGetProperty("assets", out var assets))
        {
            foreach (var a in assets.EnumerateArray())
            {
                string? name = a.TryGetProperty("name", out var n) ? n.GetString() : null;
                string? url2 = a.TryGetProperty("browser_download_url", out var u) ? u.GetString() : null;
                if (name is not null && url2 is not null
                    && name.EndsWith("-win-x64.zip", StringComparison.OrdinalIgnoreCase))
                {
                    return new UpdateCheck(new UpdateInfo(StripV(tag), url2), NoRelease: false);
                }
            }
        }
        return new UpdateCheck(null, NoRelease: false); // 没有 win-x64 zip（异常发布物），按无更新处理
    }

    // ---------- 下载 ----------

    /// <summary>流式下载更新 zip 到 %TEMP%（Content-Length 有值时报百分比，250ms 节流），返回落盘路径。
    /// notice 回调在调用方的同步上下文里执行（无 ConfigureAwait(false)，UI 线程可直接刷状态栏）。
    /// 失败时半截文件自清理后原样上抛。</summary>
    public static async Task<string> DownloadAsync(UpdateInfo info, Action<string> notice, CancellationToken ct)
    {
        string dest = Path.Combine(Path.GetTempPath(), $"WindowMerger-update-{SafeFileName(info.Version)}.zip");
        try
        {
            using var resp = await Http.GetAsync(info.ZipUrl, HttpCompletionOption.ResponseHeadersRead, ct);
            resp.EnsureSuccessStatusCode();
            long? total = resp.Content.Headers.ContentLength;
            await using var src = await resp.Content.ReadAsStreamAsync(ct);
            await using var dst = File.Create(dest);

            var buf = new byte[64 * 1024];
            long done = 0;
            long lastTick = Environment.TickCount64;
            int read;
            while ((read = await src.ReadAsync(buf, ct)) > 0)
            {
                await dst.WriteAsync(buf.AsMemory(0, read), ct);
                done += read;
                if (Environment.TickCount64 - lastTick >= 250)
                {
                    lastTick = Environment.TickCount64;
                    notice(ProgressText(done, total));
                }
            }
            notice(ProgressText(done, total));
            return dest;
        }
        catch
        {
            TryDelete(dest); // 句柄已随内层作用域释放，半截下载不残留
            throw;
        }
    }

    private static string ProgressText(long done, long? total)
        => total is > 0 ? $"下载更新中 {done * 100 / total.Value}%" : $"下载更新中 {done / 1024} KB";

    private static string SafeFileName(string s) => string.Concat(s.Split(Path.GetInvalidFileNameChars()));

    // ---------- 换装（宿主 Closing 清理完成后调用） ----------

    /// <summary>当前 exe 完整路径（单文件下 Assembly.Location 为空，必须用 ProcessPath）。</summary>
    public static string ExePath()
        => Environment.ProcessPath ?? throw new InvalidOperationException("取当前 exe 路径失败");

    /// <summary>换装三步：解出 exe → 旧 exe 改名 .old → 新 exe 落位原路径并拉起新实例（无参启动：
    /// 子窗口已被宿主还原、配置已落盘）。任何失败原样上抛；第二步失败先把旧 exe 改名回去，
    /// 让调用方（Closing）取消关闭、状态不丢。</summary>
    public static void InstallAndRestart(string zipPath)
    {
        string exe = ExePath();
        string update = exe + ".update";
        ExtractExe(zipPath, update);

        string old = exe + ".old";
        File.Move(exe, old, overwrite: true); // 上次更新残留的 .old 一并覆盖（未被占用时）
        try
        {
            File.Move(update, exe);
        }
        catch
        {
            File.Move(old, exe); // 回滚改名，宿主保持完整可继续运行
            throw;
        }
        Process.Start(new ProcessStartInfo(exe)
        {
            UseShellExecute = true,
            WorkingDirectory = Path.GetDirectoryName(exe),
        });
    }

    /// <summary>把 zip 里的 exe 解到 destPath（与目标同目录同卷：保证后续 move 原子生效），
    /// zip CRC 校验内建，损坏包在这里抛 InvalidDataException。</summary>
    public static void ExtractExe(string zipPath, string destPath)
    {
        using var zip = ZipFile.OpenRead(zipPath);
        var entry = zip.GetEntry(ZipEntryName)
            ?? throw new InvalidDataException($"更新包缺少 {ZipEntryName}");
        entry.ExtractToFile(destPath, overwrite: true);
    }

    // ---------- 残留清理（新实例启动时） ----------

    /// <summary>清理上次更新的残留文件。返回 false 表示有删不掉的（.old 可能仍被退出中的
    /// 旧进程占用），调用方应定时重试。</summary>
    public static bool CleanupLeftovers()
    {
        string exe = ExePath();
        bool ok = TryDelete(exe + ".old");
        ok &= TryDelete(exe + ".update");
        try
        {
            foreach (string zip in Directory.GetFiles(Path.GetTempPath(), "WindowMerger-update-*.zip"))
            {
                TryDelete(zip);
            }
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            // TEMP 不可枚举等，无关紧要
        }
        return ok;
    }

    private static bool TryDelete(string path)
    {
        try
        {
            if (File.Exists(path)) File.Delete(path);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return false; // 被占用（旧进程还在跑）或无权限，留给重试
        }
        return true;
    }
}
