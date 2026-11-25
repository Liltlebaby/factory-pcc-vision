param([int]$Port = 8011)
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot

# --- ปิดอินสแตนซ์เดิมก่อน (เพิ่ม 2026-09-21) ---------------------------------
# run.py ถือ lock ไฟล์ไว้หนึ่งตัวต่อโฟลเดอร์บันทึก ถ้าตัวเก่ายังรันอยู่
# ตัวใหม่จะตายด้วย 'Rack Monitor already running for this recording directory'
# แล้วคนมักไปสั่ง python -m rack_ai.run เองเพื่อให้มันขึ้น ซึ่งข้าม env ทั้งบล็อก
# ด้านล่างนี้ไปทั้งหมด จบที่บริการขึ้นมาแบบไม่มีกล้องและใช้โมเดลผิดตัว
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
$stopped = $false
foreach ($listener in $listeners) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($owner) {
        Write-Host "Stopping previous Rack Monitor: $($owner.ProcessName) (PID $($owner.Id)) on port $Port"
        Stop-Process -Id $owner.Id -Force
        $stopped = $true
    }
}
# รอให้ระบบปฏิบัติการปล่อย lock ไฟล์และพอร์ตจริง ๆ ก่อนเริ่มตัวใหม่
if ($stopped) { Start-Sleep -Seconds 4 }
# -----------------------------------------------------------------------------
$serverCameraConfigPath = 'C:\Factory\secrets\.env.camera.local'
$legacyCameraConfigPath = 'C:\Factory\config\.env.camera.local'
$cameraConfigPath = if ($env:FACTORY_CAMERA_CONFIG) { $env:FACTORY_CAMERA_CONFIG }
    elseif (Test-Path -LiteralPath $serverCameraConfigPath) { $serverCameraConfigPath }
    else { $legacyCameraConfigPath }
if (-not (Test-Path -LiteralPath $cameraConfigPath)) { throw 'Existing local camera configuration was not found.' }
$cameraValues = @{}
foreach ($configLine in Get-Content -LiteralPath $cameraConfigPath) {
    if ($configLine -match '^([A-Z0-9_]+)=(.*)$') { $cameraValues[$matches[1]] = $matches[2].Trim() }
}
foreach ($key in @('NVR_HOST','NVR_RTSP_PORT','NVR_CHANNEL','NVR_VIEWER_USERNAME','NVR_VIEWER_PASSWORD')) {
    if ([string]::IsNullOrWhiteSpace($cameraValues[$key])) { throw "Missing setting: $key" }
}
$cameraUser = [uri]::EscapeDataString($cameraValues['NVR_VIEWER_USERNAME'])
$cameraPassword = [uri]::EscapeDataString($cameraValues['NVR_VIEWER_PASSWORD'])
$env:CAMERA_RTSP_AI = "rtsp://${cameraUser}:${cameraPassword}@$($cameraValues['NVR_HOST']):$($cameraValues['NVR_RTSP_PORT'])/Streaming/Channels/$($cameraValues['NVR_CHANNEL'])"
# บ่อสุดท้ายอยู่ Dahua DVR 192.168.1.64 ไม่ใช่ Hikvision NVR_HOST ของกล้องนับเก๊ะ (.68)
# ช่อง 11 substream (Dahua realmonitor) ใช้ preview และ AI ทดลอง
# งานตรวจหมวกยังไม่แจ้งเตือน แต่การไม่พบคนในพื้นที่บ่อเกิน 5 นาทีจะบันทึกเหตุการณ์
# ใช้บัญชี viewer เดิมก่อน; หาก DVR นี้ใช้บัญชีต่างกัน ตั้ง FINAL_POND_RTSP แยก
# โดยไม่ส่ง RTSP URL หรือรหัสผ่านไปยัง browser
if ([string]::IsNullOrWhiteSpace($env:FINAL_POND_RTSP)) {
    $env:FINAL_POND_RTSP = "rtsp://${cameraUser}:${cameraPassword}@192.168.1.64:554/cam/realmonitor?channel=11&subtype=1"
}
$peeModelPath = Join-Path $projectDirectory 'models/best_PEE_V1.pt'
if ([string]::IsNullOrWhiteSpace($env:FINAL_POND_PPE_MODEL) -and (Test-Path -LiteralPath $peeModelPath)) {
    $env:FINAL_POND_PPE_MODEL = $peeModelPath
}

# --- งานเฝ้าพื้นที่บ่อสุดท้าย (เพิ่ม 2026-10-03) --------------------------------
# ใช้ yolo11s แบบ OpenVINO ตรวจคนแทน best_PEE_V1 ซึ่งตีกองกระสอบปูนเป็นคน
# ทดสอบกับภาพกล้อง 11 จริง 136 เฟรม: เจอคนในพื้นที่ครบสุด และไม่ตีกระสอบเป็นคน
# ต้องเป็น OpenVINO ไม่ใช่ PyTorch: รัน PyTorch สองโมเดลในโปรเซสเดียวกับตัวนับเก๊ะ
# ทำให้นับเก๊ะช้าจาก ~60 ms เป็น ~230 ms ต่อภาพ (ทำ 5 FPS ไม่ทัน)
# ถอยกลับ: ตั้ง $env:FINAL_POND_USE_PEE = '1' ก่อนเรียกสคริปต์ จะกลับไปใช้ best_PEE_V1
# (ตั้ง env เป็นค่าว่างใน PowerShell คือการลบตัวแปร จึงใช้ธงแยกแทน)
$personModelPath = Join-Path $projectDirectory 'models/pretrained/yolo11s_openvino_model'
if ($env:FINAL_POND_USE_PEE -ne '1' -and [string]::IsNullOrWhiteSpace($env:FINAL_POND_PERSON_MODEL) -and (Test-Path -LiteralPath $personModelPath)) {
    python -c "import openvino" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $env:FINAL_POND_PERSON_MODEL = $personModelPath
        $env:FINAL_POND_AREA_FPS = '2'
        # กล่องคนจริงของ yolo11s บางกล่องได้ 0.36-0.41 เกณฑ์ 0.45 เดิมจะตัดคนจริงทิ้ง
        $env:FINAL_POND_WORKER_CONFIDENCE = '0.35'
        # ให้เธรด OpenMP ของ PyTorch (ตัวนับเก๊ะ) ปล่อย CPU ทันที ไม่วนรอแย่ง OpenVINO
        $env:KMP_BLOCKTIME = '0'
    } else {
        Write-Warning 'openvino ยังไม่ได้ติดตั้ง (pip install openvino) — บ่อสุดท้ายใช้ best_PEE_V1 ต่อไปก่อน'
    }
}
$env:FINAL_POND_EVIDENCE_DIR = Join-Path $projectDirectory 'rack_ai/data/final_pond/evidence'
# -----------------------------------------------------------------------------
$env:RACK_PORT = "$Port"
$env:RACK_HOST = '0.0.0.0'
# ลดภาระ CPU ของ AI บ่อสุดท้ายเหลือ 0.8 FPS; ไม่เปลี่ยน FPS กล้องนับเก๊ะ
$env:FINAL_POND_PPE_FPS = '0.8'
$env:FINAL_POND_ABSENT_SECONDS = '300'
# ช่วงพักเที่ยง (เวลาไทย) ไม่นับเวลาไม่มีคนและไม่เตือน หมดพักแล้วนับ 5 นาทีใหม่ (เพิ่ม 2026-10-05)
# หลายช่วงคั่นด้วย , เช่น '12:00-13:00,17:00-17:30' · ปิดการยกเว้น: ตั้งเป็น ''
$env:FINAL_POND_QUIET_HOURS = '12:00-13:00'
# IP ที่เครื่องอื่นใช้เปิด PCC/Vision Monitor — ต้องอยู่ใน PCC_ORIGINS ไม่งั้นปุ่มใน PCC ถูกปฏิเสธ (origin_not_allowed)
# หาเองจาก IP ของเครื่องในวงโรงงาน 192.168.1.0/23 (แก้ 2026-10-05) เดิมฝัง 192.168.1.50 ไว้
# ทำให้ทุกครั้งที่ลงโค้ดใหม่บน server (192.168.1.51) ต้องตามแก้ไฟล์นี้ซ้ำ
# บังคับค่าเองได้ด้วย $env:FACTORY_PUBLIC_HOST
$publicHost = if ($env:FACTORY_PUBLIC_HOST) { $env:FACTORY_PUBLIC_HOST.Trim() } else {
    $lanAddress = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -match '^192\.168\.3[01]\.' } |
        Sort-Object { if ($_.InterfaceAlias -match 'Wi-?Fi|Wireless') { 1 } else { 0 } } |
        Select-Object -First 1 -ExpandProperty IPAddress
    if ($lanAddress) { $lanAddress } else { '192.168.1.50' }
}
Write-Host "Public host for PCC links and origins: $publicHost"
$env:PCC_PUBLIC_URL = "http://${publicHost}:3000"
$env:PCC_ORIGINS = "http://localhost:$Port,http://127.0.0.1:$Port,http://${publicHost}:$Port,http://localhost:3000,http://127.0.0.1:3000,http://${publicHost}:3000,http://localhost:3001"

# --- โมเดลนับเก๊ะ (แก้ 2026-09-15) -------------------------------------------
# best_v3.pt: YOLO11n 150 epochs, dataset rack v3 (1,048 ภาพ กลางวัน+กลางคืน)
# ตรวจแล้ว 117 นาที 46 เก๊ะ ตรงกับที่คนนับทั้งหมด; กลางวันจาก 1/5 เป็น 5/5
# ถอยกลับ: ชี้ RACK_MODEL_PATH ไปที่ models/best_backup_20260915.pt
#          แล้วเปลี่ยน RACK_IMGSZ เป็น 640 และ RACK_CONFIDENCE เป็น 0.25
$modelPath = Join-Path $projectDirectory 'models/best_v3.pt'
# ถ้าไฟล์หาย config.py จะถอยไปใช้ best.pt ตัวเก่าเงียบ ๆ จึงหยุดตรงนี้ให้เห็นชัด
if (-not (Test-Path -LiteralPath $modelPath)) { throw "Model file not found: $modelPath" }
$env:RACK_MODEL_PATH = $modelPath

# ต้องเท่ากับขนาดที่เทรน ไม่งั้นความแม่นยำตกโดยไม่มีอะไรฟ้อง
# โมเดลเก่าเทรนที่ 640, best_v3 เทรนที่ 512
$env:RACK_IMGSZ = '512'

# 0.55 คือค่าที่ใช้ตรวจสอบทั้ง 117 นาที ค่าเดิม 0.25 ไม่เคยถูกวัด
# และปล่อยกล่องคะแนนต่ำผ่านเข้ามามาก เสี่ยงนับเกิน
$env:RACK_CONFIDENCE = '0.55'

# 0.35 ลบเก๊ะตัวที่อยู่ข้างหลังทิ้งตั้งแต่ก่อน tracking เมื่อสองเก๊ะเคลื่อนที่ติดกัน
$env:RACK_IOU = '0.70'

# spatial = ระงับเฉพาะการข้ามเส้นซ้ำที่กล่องทับกันจริง
# global = ระงับทุกการข้ามเส้นในช่วง cooldown (กลืนเก๊ะที่ตามมาติด ๆ)
$env:COUNT_DEDUPE = 'spatial'
# -----------------------------------------------------------------------------

# --- ดึงภาพกล้องผ่าน TCP (เพิ่ม 2026-09-25) ----------------------------------
# ค่าเดิมของ OpenCV ใช้ UDP ถ้าแพ็กเก็ตหายระหว่างทาง (เครื่องนี้ต่อ Wi-Fi) ภาพจะแตก
# log ขึ้น 'cabac decode ... failed' / 'error while decoding MB' และสตรีมเงียบจน timeout
# ต้องตัดต่อใหม่ทุก 5-20 นาที ช่วงละ ~7 วินาทีที่ไม่ได้นับ TCP ส่งซ้ำแพ็กเก็ตที่หายให้เอง
# ถอยกลับ: ลบบรรทัด $env:OPENCV_FFMPEG_CAPTURE_OPTIONS ข้างล่างแล้วรีสตาร์ท
$env:OPENCV_FFMPEG_CAPTURE_OPTIONS = 'rtsp_transport;tcp'
# -----------------------------------------------------------------------------

Push-Location -LiteralPath $projectDirectory
try { python -m rack_ai.run } finally { Pop-Location }
