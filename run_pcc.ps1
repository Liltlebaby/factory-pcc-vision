# เปิดหน้าจอ Production Control Center
#
# เป็นเว็บ Next.js เปิดที่ http://localhost:3000
# กด Ctrl+C ในหน้าต่างนี้เพื่อหยุด
#
# หน้ารายงานนับเก๊ะกับสถานะกล้องจะขึ้นข้อมูลจริงก็ต่อเมื่อ
# Vision Monitor รันอยู่ด้วย ถ้าไม่ได้เปิดไว้ หน้าพวกนั้นจะขึ้นว่าติดต่อไม่ได้
# ซึ่งถูกต้องแล้ว ไม่ใช่ระบบพัง

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot 'PCC')

if (-not (Test-Path 'node_modules')) {
  Write-Host 'ยังไม่มี node_modules กำลังติดตั้ง...' -ForegroundColor Yellow
  npm install
}

Write-Host ''
Write-Host 'กำลังเปิด PCC ที่ http://localhost:3000' -ForegroundColor Green
Write-Host 'รอจนขึ้นคำว่า Ready แล้วค่อยเปิดเบราว์เซอร์' -ForegroundColor Green
Write-Host ''

npm run dev
