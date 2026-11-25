"""Safe import of finalized CCTV files into the RAW recording catalogue."""
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2

from .store import sha256

ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}
MAX_UPLOAD_BYTES = 5 * 1024**3


def clean_name(filename: str) -> tuple[str, str]:
    leaf=Path(filename).name
    extension=Path(leaf).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError('supported_video_extensions: mp4,mov,avi,mkv,m4v')
    name=re.sub(r'[^\w .-]+','_',Path(leaf).stem,flags=re.UNICODE).strip(' .-_')[:100]
    return name or 'uploaded_cctv',extension


def inspect_video(path: Path) -> dict:
    capture=cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():raise ValueError('uploaded_video_unreadable')
        fps=float(capture.get(cv2.CAP_PROP_FPS));frames=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not (0 < fps <= 240 and frames > 0 and width > 0 and height > 0):
            raise ValueError('uploaded_video_metadata_invalid')
        for index in sorted({0,frames//2,max(0,frames-2)}):
            capture.set(cv2.CAP_PROP_POS_FRAMES,index)
            ok,frame=capture.read()
            if not ok or frame is None:raise ValueError('uploaded_video_decode_check_failed')
        return dict(fps=fps,frames_written=frames,resolution=f'{width}x{height}',
                    duration_seconds=frames/fps,video_duration_seconds=frames/fps)
    finally:capture.release()


def finalize_upload(store,temp: Path,filename: str,size: int) -> dict:
    name,extension=clean_name(filename)
    if size <= 0:raise ValueError('empty_upload')
    if size > MAX_UPLOAD_BYTES:raise ValueError('upload_exceeds_5GB')
    info=inspect_video(temp);digest=sha256(temp)
    for clip in store.list():
        if clip.get('sha256')==digest and clip.get('status')!='archived':
            raise ValueError('video_already_imported:'+clip['clip_id'])
    clip_id='clip_'+uuid.uuid4().hex
    destination=store.root/'raw'/(clip_id+extension)
    temp.replace(destination)
    now=datetime.now(timezone.utc).isoformat()
    value=dict(clip_id=clip_id,camera='Camera09',name=name,original_filename=Path(filename).name,
               source='upload',start_time=now,end_time=now,status='recorded',raw=True,
               file_path=str(destination.relative_to(store.root)).replace('\\','/'),encoder='uploaded_original',
               uploaded_bytes=size,sha256=digest,error=None,
               note='Imported finalized RAW CCTV file; timestamps are upload time, not camera capture time.',**info)
    store.save(value)
    return value


def ensure_upload_capacity(root: Path,content_length: int | None) -> None:
    if content_length is not None and (content_length <= 0 or content_length > MAX_UPLOAD_BYTES):
        raise ValueError('invalid_or_oversized_upload')
    required=(content_length or 512*1024**2)+1024**3
    if shutil.disk_usage(root).free < required:raise OSError('insufficient_disk_space_for_upload')
