param(
    [string]$ProjectRoot = 'C:\Factory\123',
    [string]$SecretsRoot = 'C:\Factory\secrets',
    [string]$Destination = 'C:\Factory\transfer',
    # Copying the live SQLite journal while Vision Monitor writes to it can capture a
    # half-written file. With this switch the script pauses Vision Monitor for the copy
    # and starts it again; without it the script refuses while port 8011 is listening.
    [switch]$StopVision,
    # Recordings are raw video and can be many GB; counts, events and evidence are kept either way.
    [switch]$SkipRecordings
)

# Run on the OLD server. Collects what the release zip deliberately leaves out:
#   secrets\.env.camera.local   DVR credentials
#   123\PCC\.env.local          Supabase keys, PCC_SYNC_TOKEN, PCC_TELEMETRY_TOKEN, URLs
#   123\rack_ai\data\           rack count journal, AI events, evidence images, datasets
# into one folder with the same layout as C:\Factory, to copy onto the new server.
# Nothing is printed from the secret files. Delete the folder (and the USB copy) after use.

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $Destination "secrets-data-$stamp"
$taskName = 'Factory Vision PCC Watchdog'

$visionListening = @(Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue).Count -gt 0
if ($visionListening -and -not $StopVision) {
    throw 'Vision Monitor (port 8011) is running. Re-run with -StopVision to pause it during the copy (about 1-5 minutes).'
}

foreach ($required in (Join-Path $SecretsRoot '.env.camera.local'), (Join-Path $ProjectRoot 'PCC\.env.local')) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}

New-Item -ItemType Directory -Path (Join-Path $target 'secrets'), (Join-Path $target '123\PCC') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $SecretsRoot '.env.camera.local') -Destination (Join-Path $target 'secrets\.env.camera.local')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'PCC\.env.local') -Destination (Join-Path $target '123\PCC\.env.local')

$watchdog = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$paused = $false
try {
    if ($visionListening) {
        if ($watchdog) { Disable-ScheduledTask -TaskName $taskName | Out-Null }
        Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
        $paused = $true
        Start-Sleep -Seconds 5
        Write-Output "Vision Monitor paused at $(Get-Date -Format 'HH:mm:ss')"
    }
    $source = Join-Path $ProjectRoot 'rack_ai\data'
    if (Test-Path -LiteralPath $source) {
        $arguments = @($source, (Join-Path $target '123\rack_ai\data'), '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:2', '/W:2')
        if ($SkipRecordings) { $arguments += @('/XD', 'recordings') }
        robocopy @arguments | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "rack_ai\data copy failed (robocopy $LASTEXITCODE)" }
    } else {
        Write-Warning "No rack_ai\data at $source"
    }
} finally {
    if ($paused) {
        if ($watchdog) {
            Enable-ScheduledTask -TaskName $taskName | Out-Null
            Start-ScheduledTask -TaskName $taskName
        } else {
            Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $ProjectRoot 'start_factory_services.ps1'))
        }
        Write-Output "Vision Monitor restarted at $(Get-Date -Format 'HH:mm:ss')"
    }
}

$files = Get-ChildItem -LiteralPath $target -Recurse -File
$size = ($files | Measure-Object Length -Sum).Sum
@"
ไฟล์รหัสผ่านและข้อมูลจาก server เดิม ($env:COMPUTERNAME) เมื่อ $(Get-Date -Format 'yyyy-MM-dd HH:mm')

คัดลอกโฟลเดอร์นี้ทั้งหมดลง C:\Factory\ ของเครื่องใหม่ (โครงสร้างตรงกันแล้ว):
  secrets\.env.camera.local    -> C:\Factory\secrets\.env.camera.local
  123\PCC\.env.local           -> C:\Factory\123\PCC\.env.local
  123\rack_ai\data\            -> C:\Factory\123\rack_ai\data\

ถ้าเครื่องใหม่ใช้ IP อื่น: แก้ NEXT_PUBLIC_RACK_MONITOR_URL ใน PCC\.env.local แล้ว npm run build ใหม่
มีรหัสผ่านอยู่ข้างใน ห้ามส่งทางแชท/อีเมล ลบออกจาก USB และจาก C:\Factory\transfer หลังใช้
"@ | Set-Content -LiteralPath (Join-Path $target 'README_TH.txt') -Encoding UTF8

Write-Output ("Export: {0}  ({1} files, {2:N0} MB)" -f $target, $files.Count, ($size / 1MB))
Write-Output 'Contains passwords: copy by USB only, then delete this folder and the USB copy.'
