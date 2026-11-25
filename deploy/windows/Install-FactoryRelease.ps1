param(
    [Parameter(Mandatory)][string]$Archive,
    [string]$ProjectRoot = 'C:\Factory\123',
    [switch]$Apply,
    [switch]$BuildPcc
)

$ErrorActionPreference = 'Stop'
$Archive = (Resolve-Path -LiteralPath $Archive).Path
if (-not [IO.Path]::IsPathRooted($ProjectRoot)) { throw 'ProjectRoot must be an absolute path.' }
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$incomingRoot = Join-Path (Split-Path -Parent $ProjectRoot) 'incoming'
New-Item -ItemType Directory -Path $incomingRoot -Force | Out-Null
$stage = Join-Path $incomingRoot ([IO.Path]::GetFileNameWithoutExtension($Archive))
if (-not (Test-Path -LiteralPath $stage)) {
    New-Item -ItemType Directory -Path $stage | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $relative = $entry.FullName -replace '\\','/'
            if (-not $relative -or $relative.EndsWith('/')) { continue }
            $parts = $relative -split '/'
            if ($relative.StartsWith('/') -or ($parts | Where-Object { $_ -in @('','.', '..') -or $_ -match '[<>:"|?*\x00-\x1f]' })) { throw "Unsafe archive entry: $relative" }
            $destination = Join-Path $stage ($relative -replace '/','\')
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $false)
        }
    } finally { $zip.Dispose() }
}

function Get-Sha256([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    try {
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
        finally { $hasher.Dispose() }
    } finally { $stream.Dispose() }
}

$manifestPath = Join-Path $stage 'release-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Release manifest missing.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.Count -lt 20) { throw 'Release manifest unexpectedly small.' }
foreach ($entry in $manifest) {
    $relative = [string]$entry.path
    $parts = $relative -split '/'
    if ($relative.StartsWith('/') -or ($parts | Where-Object { $_ -in @('','.', '..') -or $_ -match '[<>:"|?*\x00-\x1f]' })) {
        throw "Unsafe release path: $relative"
    }
    $file = Join-Path $stage ($relative -replace '/','\')
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Release file missing: $relative" }
    if ((Get-Item -LiteralPath $file).Length -ne [long]$entry.bytes) { throw "Size mismatch: $relative" }
    if ((Get-Sha256 $file) -ne $entry.sha256) { throw "Hash mismatch: $relative" }
}
Write-Output "Verified $($manifest.Count) files in $stage"
if (-not $Apply) {
    Write-Output 'Staged only. No live services or files were changed.'
    return
}

# This intentionally refuses to replace code while either service or its watchdog is active.
foreach ($port in @(3000,8011)) {
    if (@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).Count -gt 0) {
        throw "Port $port is active. Stop services in a maintenance window before -Apply."
    }
}
$watchdog = Get-ScheduledTask -TaskName 'Factory Vision PCC Watchdog' -ErrorAction SilentlyContinue
if ($watchdog -and $watchdog.Settings.Enabled) {
    throw 'Disable Factory Vision PCC Watchdog before -Apply; re-enable it after verification.'
}

New-Item -ItemType Directory -Path $ProjectRoot -Force | Out-Null
foreach ($entry in $manifest) {
    $relative = [string]$entry.path -replace '/','\'
    $source = Join-Path $stage $relative
    $destination = Join-Path $ProjectRoot $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}
Write-Output "Installed release files to $ProjectRoot"
Write-Output 'Preserved PCC/.env.local, rack_ai/data, and external secrets.'
if ($BuildPcc) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'PCC\.env.local'))) {
        throw 'PCC/.env.local is missing. Configure server-local secrets before building.'
    }
    Push-Location (Join-Path $ProjectRoot 'PCC')
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'PCC build failed.' }
    } finally { Pop-Location }
}
Write-Output 'Install complete. Start services and verify counts, camera preview, and PCC health.'
