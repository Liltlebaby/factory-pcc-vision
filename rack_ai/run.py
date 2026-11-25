import logging
import os
from dotenv import load_dotenv
from pathlib import Path
from .runtime import InstanceLock, JsonFormatter


REQUIRED = (
    # ไม่มีค่านี้ = ไม่มีแหล่งภาพ บริการจะขึ้นมาแล้วค้างที่ error='starting'
    # กับ camera_unavailable ตลอดไป ซึ่งหน้าจอแยกไม่ออกจากกล้องหลุดจริง
    ('CAMERA_RTSP_AI', 'CAMERA_SOURCE'),
    # ไม่มีค่านี้ config.py จะถอยไปใช้ best.pt ตัวเก่าเงียบ ๆ
    # ทำให้รันอยู่คนละโมเดลกับที่ตรวจสอบไว้โดยไม่มีอะไรฟ้อง
    ('RACK_MODEL_PATH',),
)


def check_configuration():
    """หยุดตั้งแต่ต้นเมื่อ env หลักหาย แทนที่จะรันต่อแบบพิการเงียบ ๆ

    เคสจริง: สตาร์ทด้วย `python -m rack_ai.run` ตรง ๆ แทนที่จะผ่าน
    start_camera09.ps1 บริการขึ้นปกติ ตอบ API ได้ แต่ไม่มีภาพและใช้โมเดลผิดตัว
    กว่าจะรู้ก็เสียเวลาไล่หาที่กล้องกับ NVR ทั้งที่ต้นเหตุอยู่ตรงนี้
    ตั้ง RACK_ALLOW_UNCONFIGURED=1 เพื่อข้าม เมื่อจงใจรันแบบไม่มีกล้อง
    """
    if os.getenv('RACK_ALLOW_UNCONFIGURED'):
        return
    missing = [names[0] for names in REQUIRED if not any(os.getenv(name) for name in names)]
    if missing:
        raise SystemExit(
            'Missing required configuration: ' + ', '.join(missing) + '. '
            'Start the service with rack_ai/start_camera09.ps1, which sets these, '
            'or set RACK_ALLOW_UNCONFIGURED=1 to run without a camera on purpose.'
        )


if __name__ == '__main__':
    load_dotenv('rack_ai/.env')
    check_configuration()
    logging.basicConfig(level=logging.INFO)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(JsonFormatter())
    import uvicorn
    # One worker only: additional workers would open duplicate camera readers.
    with InstanceLock(Path(os.getenv('RECORD_ROOT','rack_ai/data/recordings'))):
        uvicorn.run(
            'rack_ai.app:app',
            host=os.getenv('RACK_HOST', '127.0.0.1'),
            port=int(os.getenv('RACK_PORT','8011')),
            workers=1,
            access_log=False,
        )
