param(
    [string]$ProjectRoot = 'C:\Factory\123',
    [string]$BackupRoot = 'C:\Factory\backups'
)

# Snapshot the installed code before Install-FactoryRelease.ps1 -Apply overwrites it.
# Install copies files over the old ones and keeps no copy, so without this there is
# no way back if the new release misbehaves on the floor.
#
# Kept:     PCC (with its .next build, so a rollback needs no rebuild), rack_ai code,
#           models, root launch scripts, PCC/.env.local.
# Not kept: PCC/node_modules (unchanged by this release), rack_ai/data (live journal
#           and recordings - never restored over newer data), logs.

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $BackupRoot "code-$stamp"
New-Item -ItemType Directory -Path $target -Force | Out-Null

function Copy-Tree([string]$relative, [string[]]$excludeDirs) {
    $source = Join-Path $ProjectRoot $relative
    if (-not (Test-Path -LiteralPath $source)) { Write-Warning "skip (not found): $relative"; return }
    $arguments = @($source, (Join-Path $target $relative), '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')
    if ($excludeDirs) { $arguments += '/XD'; $arguments += $excludeDirs }
    robocopy @arguments | Out-Null
    # robocopy: 0-7 = success, 8+ = failure
    if ($LASTEXITCODE -ge 8) { throw "backup failed for $relative (robocopy $LASTEXITCODE)" }
}

Copy-Tree 'PCC' @('node_modules')
Copy-Tree 'rack_ai' @('data', '__pycache__')
Copy-Tree 'models' @()
Copy-Tree 'deploy' @()
foreach ($file in 'start_factory_services.ps1', 'run_pcc.ps1', 'AGENTS.md') {
    $source = Join-Path $ProjectRoot $file
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $target }
}

$size = (Get-ChildItem -LiteralPath $target -Recurse -File | Measure-Object Length -Sum).Sum
Write-Output ("Backup: {0}  ({1:N0} MB)" -f $target, ($size / 1MB))
Write-Output 'Rollback: stop services, robocopy this folder back over the project root, start services.'
