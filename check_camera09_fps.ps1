# ตรวจว่า FPS กล้องนับเก๊ะที่แกว่ง เป็นเพราะกล้อง/DVR หรือเพราะระบบ
#
# รันตอนที่ Vision Monitor ทำงานอยู่ และให้มีเก๊ะเลื่อนผ่านระหว่างวัด
# ใช้ค่ากล้องชุดเดียวกับ start_camera09.ps1 ไม่พิมพ์รหัสผ่านออกมา
#
#   powershell -ExecutionPolicy Bypass -File .\check_camera09_fps.ps1
#   powershell -ExecutionPolicy Bypass -File .\check_camera09_fps.ps1 -Seconds 300 -Transport tcp

param([int]$Seconds = 120, [ValidateSet('default','tcp','udp')][string]$Transport = 'default')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$serverCameraConfigPath = 'C:\Factory\secrets\.env.camera.local'
$legacyCameraConfigPath = 'C:\Factory\config\.env.camera.local'
$cameraConfigPath = if ($env:FACTORY_CAMERA_CONFIG) { $env:FACTORY_CAMERA_CONFIG }
    elseif (Test-Path -LiteralPath $serverCameraConfigPath) { $serverCameraConfigPath }
    else { $legacyCameraConfigPath }
if (-not (Test-Path -LiteralPath $cameraConfigPath)) { throw 'ไม่พบไฟล์ตั้งค่ากล้อง .env.camera.local' }
$cameraValues = @{}
foreach ($configLine in Get-Content -LiteralPath $cameraConfigPath) {
    if ($configLine -match '^([A-Z0-9_]+)=(.*)$') { $cameraValues[$matches[1]] = $matches[2].Trim() }
}
$cameraUser = [uri]::EscapeDataString($cameraValues['NVR_VIEWER_USERNAME'])
$cameraPassword = [uri]::EscapeDataString($cameraValues['NVR_VIEWER_PASSWORD'])
$env:CAMERA_RTSP_AI = "rtsp://${cameraUser}:${cameraPassword}@$($cameraValues['NVR_HOST']):$($cameraValues['NVR_RTSP_PORT'])/Streaming/Channels/$($cameraValues['NVR_CHANNEL'])"

python -m rack_ai.tools.camera_fps_check --seconds $Seconds --transport $Transport
