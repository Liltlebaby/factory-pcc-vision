param(
    [Parameter(Mandatory)][string]$ComputerName,
    [string]$ProjectRoot = 'C:\Factory\123',
    [pscredential]$Credential,
    [switch]$Apply,
    [switch]$BuildPcc
)

$ErrorActionPreference = 'Stop'
$buildOutput = @(& (Join-Path $PSScriptRoot 'New-FactoryRelease.ps1'))
$buildOutput | Write-Output
$releaseLine = @($buildOutput | Where-Object { $_ -is [string] -and $_.StartsWith('Release: ') })
if ($releaseLine.Count -ne 1) { throw 'Could not identify release archive.' }
$archive = $releaseLine[0].Substring('Release: '.Length)
$sendArgs = @{
    ComputerName = $ComputerName
    Archive = $archive
    ProjectRoot = $ProjectRoot
    Apply = $Apply
    BuildPcc = $BuildPcc
}
if ($Credential) { $sendArgs.Credential = $Credential }
& (Join-Path $PSScriptRoot 'Send-FactoryRelease.ps1') @sendArgs
