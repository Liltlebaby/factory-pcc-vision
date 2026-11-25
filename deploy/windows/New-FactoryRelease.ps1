param(
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'artifacts\server-releases')
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'PCC\package.json'))) { throw 'PCC project not found.' }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'rack_ai\run.py'))) { throw 'Vision project not found.' }

$releaseId = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$archive = Join-Path $OutputDirectory "factory-release-$releaseId.zip"
$staging = Join-Path $OutputDirectory "stage-$releaseId"
if (Test-Path -LiteralPath $staging) { throw "Staging path already exists: $staging" }
New-Item -ItemType Directory -Path $staging | Out-Null

function Get-Sha256([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    try {
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
        finally { $hasher.Dispose() }
    } finally { $stream.Dispose() }
}

function Copy-ReleaseTree([string]$relativeRoot) {
    $source = Join-Path $ProjectRoot $relativeRoot
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing source: $source" }
    Get-ChildItem -LiteralPath $source -File -Recurse | ForEach-Object {
        $relative = $_.FullName.Substring($ProjectRoot.Length + 1)
        $parts = $relative -split '[\\/]'
        if ($parts | Where-Object { $_ -in @('node_modules','.next','.git','.venv','venv','__pycache__','data','recordings','runs','datasets','dataset','output','outputs','artifacts','service_logs','.turbo') }) { return }
        if ($_.Name -match '^(\.env($|\.)|.*\.db($|-)|.*\.sqlite($|-)|.*\.sqlite3($|-))' -or $_.Extension -in @('.pyc','.log','.mp4','.avi','.ipynb')) { return }
        $destination = Join-Path $staging $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination
    }
}

try {
    foreach ($tree in @('PCC','rack_ai','deploy','contracts')) {
        if (Test-Path -LiteralPath (Join-Path $ProjectRoot $tree)) { Copy-ReleaseTree $tree }
    }
    foreach ($relative in @(
        'ai\rack_detector\offline_track_count.py',
        'ai\rack_detector\__init__.py',
        'models\best_v3.pt',
        'models\best_PEE_V1.pt',
        'models\best.pt',
        # person detector for the final-pond work-area task (OpenVINO export, 2026-10)
        'models\pretrained\yolo11s_openvino_model\yolo11s.xml',
        'models\pretrained\yolo11s_openvino_model\yolo11s.bin',
        'models\pretrained\yolo11s_openvino_model\metadata.yaml',
        'start_factory_services.ps1',
        'run_pcc.ps1',
        'check_camera09_fps.ps1',
        'AGENTS.md'
    )) {
        $source = Join-Path $ProjectRoot $relative
        if (-not (Test-Path -LiteralPath $source)) {
            if ($relative -eq 'ai\rack_detector\__init__.py' -or $relative -eq 'models\best.pt') { continue }
            throw "Required release file missing: $source"
        }
        $destination = Join-Path $staging $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }
    $files = @(Get-ChildItem -LiteralPath $staging -File -Recurse)
    if ($files.Count -lt 20) { throw "Release unexpectedly small: $($files.Count) files" }
    $manifest = foreach ($file in $files) {
        [pscustomobject]@{
            path = ($file.FullName.Substring($staging.Length + 1) -replace '\\','/')
            bytes = $file.Length
            sha256 = Get-Sha256 $file.FullName
        }
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $staging 'release-manifest.json') -Encoding UTF8
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($staging, $archive, [IO.Compression.CompressionLevel]::Optimal, $false)
    Write-Output "Release: $archive"
    Write-Output "Files: $($files.Count)"
    Write-Output "SHA256: $(Get-Sha256 $archive)"
} finally {
    if (Test-Path -LiteralPath $staging) {
        $resolvedStage = (Resolve-Path -LiteralPath $staging).Path
        if (-not $resolvedStage.StartsWith($OutputDirectory + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe staging cleanup path.' }
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
