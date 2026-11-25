param(
    [Parameter(Mandatory)][string]$ComputerName,
    [Parameter(Mandatory)][string]$Archive,
    [string]$ProjectRoot = 'C:\Factory\123',
    [pscredential]$Credential,
    [switch]$Apply,
    [switch]$BuildPcc
)

$ErrorActionPreference = 'Stop'
$Archive = (Resolve-Path -LiteralPath $Archive).Path
$sessionArgs = @{ ComputerName = $ComputerName; ErrorAction = 'Stop' }
if ($Credential) { $sessionArgs.Credential = $Credential }
$session = New-PSSession @sessionArgs
function Get-Sha256([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    try {
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
        finally { $hasher.Dispose() }
    } finally { $stream.Dispose() }
}
try {
    $remoteIncoming = Invoke-Command -Session $session -ScriptBlock {
        param($root)
        if (-not [IO.Path]::IsPathRooted($root)) { throw 'ProjectRoot must be absolute.' }
        $incoming = Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($root))) 'incoming'
        New-Item -ItemType Directory -Path $incoming -Force | Out-Null
        return $incoming
    } -ArgumentList $ProjectRoot
    $remoteArchive = Join-Path $remoteIncoming (Split-Path -Leaf $Archive)
    Copy-Item -LiteralPath $Archive -Destination $remoteArchive -ToSession $session -Force
    $localHash = Get-Sha256 $Archive
    $remoteHash = Invoke-Command -Session $session -ScriptBlock {
        param($path)
        $stream = [IO.File]::OpenRead($path)
        try {
            $hasher = [Security.Cryptography.SHA256]::Create()
            try { ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
            finally { $hasher.Dispose() }
        } finally { $stream.Dispose() }
    } -ArgumentList $remoteArchive
    if ($localHash -ne $remoteHash) { throw 'Transferred archive hash mismatch.' }
    $installer = Join-Path $PSScriptRoot 'Install-FactoryRelease.ps1'
    $remoteInstaller = Join-Path $remoteIncoming 'Install-FactoryRelease.ps1'
    Copy-Item -LiteralPath $installer -Destination $remoteInstaller -ToSession $session -Force
    Invoke-Command -Session $session -ScriptBlock {
        param($script,$archive,$root,$apply,$build)
        & $script -Archive $archive -ProjectRoot $root -Apply:$apply -BuildPcc:$build
    } -ArgumentList $remoteInstaller,$remoteArchive,$ProjectRoot,[bool]$Apply,[bool]$BuildPcc
} finally {
    Remove-PSSession $session
}
