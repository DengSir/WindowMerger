# ASCII-only: local release packaging - builds a framework-dependent single-file
# exe (win-x64) and copies it to publish\WindowMerger-<version>-win-x64.exe.
# A running instance is closed gracefully first (PostMessage WM_CLOSE, same
# path as normal exit: saves config, restores attached windows).
param(
    [string]$Version = '',
    [string]$Configuration = 'Release'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$csproj = Join-Path $root 'WindowMerger.csproj'

# --- resolve version: param wins, otherwise read <Version> from the csproj ---
if (-not $Version) {
    [xml]$doc = Get-Content -Raw -Encoding UTF8 $csproj
    $Version = @($doc.Project.PropertyGroup)[0].Version
    if (-not $Version) { throw 'Cannot read <Version> from WindowMerger.csproj; pass -Version explicitly.' }
}
Write-Output ("Version: {0}" -f $Version)

# --- close running instances gracefully (exe file lock would break the build) ---
Add-Type -Namespace PM -Name U32 -MemberDefinition '[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);'
$procs = @(Get-Process WindowMerger -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 })
foreach ($p in $procs) {
    Write-Output ("Closing running instance (pid {0}) via WM_CLOSE ..." -f $p.Id)
    [PM.U32]::PostMessage($p.MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
}
if ($procs.Count -gt 0) {
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        foreach ($p in $procs) { $p.Refresh() }
        if (@($procs | Where-Object { -not $_.HasExited }).Count -eq 0) { break }
        Start-Sleep -Milliseconds 300
    }
    $alive = @($procs | Where-Object { -not $_.HasExited })
    if ($alive.Count -gt 0) {
        throw ('Instance pid {0} did not exit within 15s; refusing to force kill. Close it manually and retry.' -f ($alive[0].Id))
    }
}

# --- publish via the committed VS publish profile (FolderProfile.pubxml = single
# --- source of truth: win-x64 / framework-dependent / single-file / PublishDir) ---
$pubProfile = Join-Path $root 'Properties\PublishProfiles\FolderProfile.pubxml'
if (-not (Test-Path $pubProfile)) { throw "Publish profile not found: $pubProfile" }
dotnet publish $csproj -c $Configuration -p:PublishProfile=FolderProfile `
    -p:TreatWarningsAsErrors=true -p:Version=$Version
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed with exit code $LASTEXITCODE." }

# profile's relative PublishDir (publish\) resolves against the project dir
$pubExe = Join-Path $root 'publish\WindowMerger.exe'
if (-not (Test-Path $pubExe)) { throw "Published exe not found: $pubExe" }

$artifactDir = Join-Path $root 'publish'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
$artifact = Join-Path $artifactDir ("WindowMerger-{0}-win-x64.exe" -f $Version)
# copy then rename-over: an instance running FROM the artifact holds an image
# lock that denies overwrite but allows rename (observed in practice)
Copy-Item $pubExe "$artifact.new" -Force
Move-Item "$artifact.new" $artifact -Force

$size = [math]::Round((Get-Item $artifact).Length / 1MB, 2)
$hash = (Get-FileHash $artifact -Algorithm SHA256).Hash
Write-Output ("ARTIFACT: {0} ({1} MB)" -f $artifact, $size)
Write-Output ("SHA256  : {0}" -f $hash)
Write-Output 'NOTE    : target machines need the .NET 10 Desktop Runtime (x64).'
Write-Output 'PUBLISH_DONE'
