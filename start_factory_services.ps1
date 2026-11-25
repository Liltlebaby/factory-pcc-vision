param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $MyInvocation.MyCommand.Path
$pccDirectory = Join-Path $workspace 'PCC'
$visionLauncher = Join-Path $workspace 'rack_ai\start_camera09.ps1'
$pccServer = Join-Path $pccDirectory '.next\standalone\server.js'
$logDirectory = Join-Path $workspace 'service_logs'

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne(1000)) { return $false }
        $client.EndConnect($connection)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$pccRunning = Test-LocalPort 3000
$visionRunning = Test-LocalPort 8011
if ($CheckOnly) {
    Write-Output "PCC port 3000: $pccRunning"
    Write-Output "Vision Monitor port 8011: $visionRunning"
    return
}

if ($pccRunning -and $visionRunning) { return }
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

if (-not $pccRunning) {
    if (-not (Test-Path -LiteralPath $pccServer)) {
        throw 'PCC production build is missing. Run npm run build in PCC first.'
    }
    $standaloneDirectory = Split-Path -Parent $pccServer
    $standaloneStatic = Join-Path $standaloneDirectory '.next\static'
    if (-not (Test-Path -LiteralPath $standaloneStatic)) {
        Copy-Item -LiteralPath (Join-Path $pccDirectory '.next\static') -Destination $standaloneStatic -Recurse
    }
    $standalonePublic = Join-Path $standaloneDirectory 'public'
    if (-not (Test-Path -LiteralPath $standalonePublic)) {
        Copy-Item -LiteralPath (Join-Path $pccDirectory 'public') -Destination $standalonePublic -Recurse
    }
    Copy-Item -LiteralPath (Join-Path $pccDirectory '.env.local') -Destination (Join-Path $standaloneDirectory '.env.local') -Force
    $env:PORT = '3000'
    $env:HOSTNAME = '0.0.0.0'
    Start-Process -FilePath 'node.exe' -ArgumentList @($pccServer) -WorkingDirectory $pccDirectory `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'pcc.stdout.log') `
        -RedirectStandardError (Join-Path $logDirectory 'pcc.stderr.log')
}

if (-not $visionRunning) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $visionLauncher) `
        -WorkingDirectory $workspace -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory 'vision.stdout.log') `
        -RedirectStandardError (Join-Path $logDirectory 'vision.stderr.log')
}
