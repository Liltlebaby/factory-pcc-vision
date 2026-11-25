"""Round-trip helpers for annotating Rack frames in Roboflow.

The exchange format is a regular YOLOv8 object-detection ZIP. Frame IDs stay
as filenames so reviewed annotations can be mapped back to SQLite.
"""
import time
import zipfile
from pathlib import PurePosixPath

import yaml

from .store import identity, validate_boxes, yolo_text


MAX_ROBOFLOW_ZIP_BYTES = 1024 * 1024 * 1024
MAX_ROBOFLOW_FILES = 10_000


def export_zip(store, status='pending'):
    if status not in ('pending', 'approved', 'all'):
        raise ValueError('invalid_roboflow_status')
    frames = [f for f in store.list('frame') if status == 'all' or f['review_status'] == status]
    if not frames:
        raise ValueError('no_frames_for_roboflow')
    root = store.path('roboflow')
    root.mkdir(parents=True, exist_ok=True)
    path = root / (identity('rack_roboflow') + '.zip')
    data = {'path': '.', 'train': 'images/train', 'val': 'images/train', 'names': {0: 'rack'}}
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('data.yaml', yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
        archive.writestr(
            'README_ROBOFLOW.txt',
            'Rack Monitor / Roboflow round-trip\n'
            'Project type: Object Detection\nClass: rack\n'
            'Keep image filenames unchanged. Export the reviewed dataset as YOLOv8.\n',
        )
        for frame in frames:
            archive.write(store.path(frame['image_path']), f"images/train/{frame['id']}.jpg")
            archive.writestr(f"labels/train/{frame['id']}.txt", yolo_text(frame['boxes']))
    return path, len(frames)


def _safe_members(archive):
    members = archive.infolist()
    if len(members) > MAX_ROBOFLOW_FILES:
        raise ValueError('roboflow_zip_too_many_files')
    total = 0
    for member in members:
        total += member.file_size
        name = PurePosixPath(member.filename.replace('\\', '/'))
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('invalid_roboflow_zip_path')
        if total > MAX_ROBOFLOW_ZIP_BYTES:
            raise ValueError('roboflow_zip_uncompressed_too_large')
    return members


def _boxes(text):
    result = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        values = line.split()
        if len(values) != 5:
            raise ValueError(f'invalid_yolo_label_line_{line_number}')
        try:
            class_id = int(values[0])
            x, y, width, height = map(float, values[1:])
        except (TypeError, ValueError):
            raise ValueError(f'invalid_yolo_label_line_{line_number}') from None
        if class_id != 0:
            raise ValueError('roboflow_project_must_only_have_rack_class_0')
        result.append([x - width / 2, y - height / 2, x + width / 2, y + height / 2])
    return validate_boxes(result)


def import_zip(store, path, actor, approve=True):
    actor = actor.strip()
    if not actor or len(actor) > 100:
        raise ValueError('invalid_review_actor')
    updated = []
    ignored = 0
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ValueError('invalid_roboflow_zip') from None
    with archive:
        members = _safe_members(archive)
        labels = {}
        for member in members:
            item = PurePosixPath(member.filename.replace('\\', '/'))
            if member.is_dir() or item.suffix.lower() != '.txt' or not item.stem.startswith('frame_'):
                continue
            if member.file_size > 2 * 1024 * 1024:
                raise ValueError('roboflow_label_too_large')
            labels[item.stem] = archive.read(member).decode('utf-8-sig')
        if not labels:
            raise ValueError('no_frame_labels_in_roboflow_zip')
        prepared = []
        for frame_id, text in labels.items():
            try:
                frame = store.get('frame', frame_id)
            except KeyError:
                ignored += 1
                continue
            prepared.append((frame, _boxes(text)))
        for frame, boxes in prepared:
            action = 'approve' if approve else 'save'
            updated.append(store.review(frame['id'], frame['revision'], action, actor, boxes, not boxes))
    return {
        'id': identity('roboflow_import'),
        'created': time.time(),
        'updated': len(updated),
        'ignored': ignored,
        'status': 'approved' if approve else 'pending',
        'frame_ids': [f['id'] for f in updated],
    }
