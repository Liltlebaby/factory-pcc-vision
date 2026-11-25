"""ยิง ISAPI ของ DVR ดูว่า endpoint ไหนตอบอะไรบ้าง ก่อนเขียนโค้ดจริง

ทำไมต้องมีสคริปต์นี้
--------------------
เฟิร์มแวร์ปี 2017 ของ DS-7216HGHI-F1 ตอบไม่ตรงเอกสาร: รายงาน deviceType เป็น
"IPC" ทั้งที่เป็น DVR 16 ช่อง และตอบ maxFrameRate เป็น 0 ทั้งที่ของจริงวิ่ง 30 fps
การเขียนโค้ดโดยเดาจากเอกสาร ISAPI จึงเสี่ยงพังเงียบ ๆ ต้องยิงดูของจริงก่อน

สิ่งที่อยากรู้จากรอบนี้
----------------------
ช่องไหนที่บอกว่า "กล้องยังมีสัญญาณอยู่ไหม" วิธีหาคือเทียบช่อง 9 (กล้องนับเก๊ะ
ที่ภาพมาปกติ) กับช่อง 12 (ที่หน้า Live View ขึ้น NO VIDEO) ฟิลด์ไหนต่างกัน
ฟิลด์นั้นคือตัวที่เราต้องใช้

รัน
---
    cd C:\\Factory\\123
    python -m rack_ai.tools.probe_isapi

อ่าน user/password/host จาก CAMERA_RTSP_AI ที่ start_camera09.ps1 ตั้งไว้
ถ้ายังไม่ได้ตั้ง ให้รันผ่าน start_camera09.ps1 ก่อน หรือส่ง URL มาทาง argument
สคริปต์นี้อ่านอย่างเดียว ไม่เขียนค่าอะไรลง DVR และไม่พิมพ์รหัสผ่านออกมา
"""
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# ช่อง 9 = กล้องนับเก๊ะ (ภาพมาปกติ) · ช่อง 12 = ช่องที่ขึ้น NO VIDEO
LIVE_CHANNEL, DEAD_CHANNEL = 9, 12

PATHS = (
    '/ISAPI/System/Video/inputs/channels',
    f'/ISAPI/System/Video/inputs/channels/{LIVE_CHANNEL}',
    f'/ISAPI/System/Video/inputs/channels/{DEAD_CHANNEL}',
    '/ISAPI/System/status',
    '/ISAPI/System/workingstatus',
    '/ISAPI/Event/triggers',
    f'/ISAPI/Streaming/channels/{LIVE_CHANNEL}01/status',
    '/ISAPI/ContentMgmt/Storage',
)

LIMIT = 900


def credentials(source: str):
    """ดึง host/user/password ออกจาก RTSP URL — ค่าถูก percent-encode มาจาก PowerShell"""
    parts = urllib.parse.urlsplit(source)
    if not parts.hostname:
        raise SystemExit('CAMERA_RTSP_AI is not a URL. Run start_camera09.ps1 first.')
    return (
        parts.hostname,
        urllib.parse.unquote(parts.username or ''),
        urllib.parse.unquote(parts.password or ''),
    )


def opener_for(host: str, user: str, password: str):
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, f'http://{host}/', user, password)
    return urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(manager),
        urllib.request.HTTPBasicAuthHandler(manager),
    )


def probe(opener, host: str, path: str):
    url = f'http://{host}{path}'
    try:
        with opener.open(url, timeout=6) as response:
            return response.status, response.read(LIMIT * 4).decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        # 401 = บัญชีนี้ไม่มีสิทธิ์อ่าน endpoint นี้ (คนละเรื่องกับ 404 ที่แปลว่าไม่มี)
        body = error.read(400).decode('utf-8', 'replace') if error.fp else ''
        return error.code, body
    except Exception as error:  # timeout, connection refused, ฯลฯ
        return None, f'{type(error).__name__}: {error}'


def compact(text: str) -> str:
    """ตัด whitespace ส่วนเกินของ XML ให้อ่านง่ายในเทอร์มินัล"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = ' '.join(lines)
    return joined[:LIMIT] + (' …' if len(joined) > LIMIT else '')


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else os.getenv('CAMERA_RTSP_AI', '')
    if not source:
        raise SystemExit(
            'CAMERA_RTSP_AI is not set. Start via rack_ai/start_camera09.ps1, '
            'or pass the RTSP URL as the first argument.'
        )
    host, user, password = credentials(source)
    print(f'DVR {host} · user {user} · read-only probe\n')

    opener = opener_for(host, user, password)
    for path in PATHS:
        status, body = probe(opener, host, path)
        label = status if status is not None else 'ERR'
        print(f'--- {label}  {path}')
        print(compact(body) or '(empty)')
        print()

    print('เทียบช่อง', LIVE_CHANNEL, '(ภาพมาปกติ) กับช่อง', DEAD_CHANNEL,
          '(NO VIDEO) ว่าฟิลด์ไหนต่างกัน — ฟิลด์นั้นคือตัวบอกสัญญาณกล้อง')


if __name__ == '__main__':
    main()
