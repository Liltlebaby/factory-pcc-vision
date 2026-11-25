"""SQLite is authoritative; exported labels are reproducible artifacts."""
import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def identity(prefix):
    return prefix+'_'+uuid.uuid4().hex


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temp.replace(path)


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_boxes(boxes):
    if len(boxes)>200:
        raise ValueError('too_many_boxes')
    clean=[]
    for box in boxes:
        if len(box)!=4 or any(not isinstance(v,(float,int)) or not math.isfinite(v) for v in box):
            raise ValueError('invalid_box')
        x1,y1,x2,y2=map(float,box)
        if not (0<=x1<x2<=1 and 0<=y1<y2<=1):
            raise ValueError('boxes_must_be_normalized_xyxy')
        clean.append([x1,y1,x2,y2])
    return clean


def yolo_text(boxes):
    return ''.join(f'0 {(a+c)/2:.8f} {(b+d)/2:.8f} {c-a:.8f} {d-b:.8f}\n'
                   for a,b,c,d in validate_boxes(boxes))


class LabStore:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(kind,id))')
            db.execute('CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY,frame_id TEXT NOT NULL,revision INTEGER NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS ai_events (cursor INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,camera_id TEXT NOT NULL,task_id TEXT NOT NULL,station_id TEXT NOT NULL,event_type TEXT NOT NULL,occurred_at REAL NOT NULL,data TEXT NOT NULL,created REAL NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_records_recent ON records(kind,updated)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_ai_events_station_cursor ON ai_events(station_id,cursor)')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.root/'lab.sqlite3',timeout=10)
        try:
            db.execute('PRAGMA busy_timeout=10000')
            with db:
                yield db
        finally:
            db.close()

    def path(self, relative):
        path=(self.root/relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('invalid_artifact_path')
        return path

    def put(self,kind,value,db=None):
        args=(kind,value['id'],json.dumps(value,ensure_ascii=False,allow_nan=False),time.time())
        if db is not None:
            db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)',args)
        else:
            with self.connect() as conn:
                conn.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)',args)

    def get(self,kind,key,db=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',key):
            raise ValueError('invalid_id')
        if db is None:
            with self.connect() as conn:
                return self.get(kind,key,conn)
        row=db.execute('SELECT data FROM records WHERE kind=? AND id=?',(kind,key)).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def list(self,kind):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM records WHERE kind=? ORDER BY updated DESC',(kind,))]

    def append_event(self,value,db=None):
        required=('event_id','camera_id','task_id','station_id','type','occurred_at')
        if any(key not in value for key in required):
            raise ValueError('invalid_ai_event')
        for key in ('event_id','camera_id','task_id','station_id','type'):
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',str(value[key])):
                raise ValueError('invalid_ai_event')
        raw_occurred_at=value['occurred_at']
        occurred_at=(datetime.fromisoformat(raw_occurred_at.replace('Z','+00:00')).timestamp()
                     if isinstance(raw_occurred_at,str) else float(raw_occurred_at))
        if not math.isfinite(occurred_at):
            raise ValueError('invalid_ai_event')
        args=(value['event_id'],value['camera_id'],value['task_id'],value['station_id'],
              value['type'],occurred_at,json.dumps(value,ensure_ascii=False,allow_nan=False),time.time())
        if db is None:
            with self.connect() as conn:
                return self.append_event(value,conn)
        db.execute('INSERT OR IGNORE INTO ai_events(event_id,camera_id,task_id,station_id,event_type,occurred_at,data,created) VALUES (?,?,?,?,?,?,?,?)',args)
        row=db.execute('SELECT cursor FROM ai_events WHERE event_id=?',(value['event_id'],)).fetchone()
        return int(row[0])

    def events(self,after=0,limit=100,station_id=None):
        after=int(after);limit=int(limit)
        if after<0 or not 1<=limit<=500:
            raise ValueError('invalid_event_page')
        if station_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',station_id):
            raise ValueError('invalid_station_id')
        where='cursor>?';args=[after]
        if station_id is not None:
            where+=' AND station_id=?';args.append(station_id)
        args.append(limit+1)
        with self.connect() as db:
            rows=db.execute(f'SELECT cursor,data FROM ai_events WHERE {where} ORDER BY cursor ASC LIMIT ?',args).fetchall()
        has_more=len(rows)>limit
        rows=rows[:limit]
        items=[]
        for cursor,data in rows:
            item=json.loads(data);item['cursor']=int(cursor);items.append(item)
        return dict(items=items,next_cursor=items[-1]['cursor'] if items else after,has_more=has_more)

    # ประเภทเหตุการณ์นับเก๊ะ — ชื่อเดิม rubber_counted ยังอยู่ในข้อมูลที่บันทึกไว้ก่อนเปลี่ยนชื่อ
    COUNT_EVENT_TYPES = ('rack_counted', 'rubber_counted')

    def count_times(self, start, end, station_id=None):
        """คืนเวลาที่นับเก๊ะได้ในช่วงที่ขอ เพื่อเอาไปแจกแจงเป็นรายชั่วโมง

        คืนแค่ timestamp ไม่ใช่ทั้ง event เพราะรายงานรายชั่วโมงใช้แค่เวลา
        และวันหนึ่งมีไม่กี่ร้อยรายการ การแจกแจงฝั่ง Python จึงถูกกว่าการทำ
        date math ใน SQL ที่ต้องยุ่งกับ timezone
        """
        start = float(start); end = float(end)
        if not start < end:
            raise ValueError('invalid_time_range')
        if station_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', station_id):
            raise ValueError('invalid_station_id')
        placeholders = ','.join('?' * len(self.COUNT_EVENT_TYPES))
        where = f'occurred_at>=? AND occurred_at<? AND event_type IN ({placeholders})'
        args = [start, end, *self.COUNT_EVENT_TYPES]
        if station_id is not None:
            where += ' AND station_id=?'; args.append(station_id)
        with self.connect() as db:
            rows = db.execute(
                f'SELECT occurred_at FROM ai_events WHERE {where} ORDER BY occurred_at ASC', args
            ).fetchall()
        return [float(row[0]) for row in rows]

    # ---- บ่อสุดท้าย: รอบตรวจแม่เหล็กและเวลาที่กล้องเห็นภาพจริง ----

    INSPECTION_EVENT_TYPES = ('magnet_inspection',)
    COVERAGE_KIND = 'camera_coverage'

    @staticmethod
    def _coverage_id(camera_id, round_key):
        # คั่นด้วย _ เพราะ : ไม่ผ่าน regex ของ records.id
        # เรียงตามตัวอักษรของ round_key ตรงกับเรียงตามเวลาพอดี จึงค้นเป็นช่วงได้
        return f'{camera_id}_{round_key}'

    def add_coverage(self, camera_id, entries, db=None):
        """บวกเวลาที่กล้องเห็นภาพเข้าไปในรอบที่ระบุ แล้วคืนยอดสะสมล่าสุด

        เป็นการบวกสะสม ไม่ใช่การเขียนทับ เพราะ worker ส่งเข้ามาเป็นช่วง ๆ
        ระหว่างชั่วโมง ถ้าเขียนทับ การรีสตาร์ต worker กลางชั่วโมงจะทำให้เวลา
        ที่เห็นภาพก่อนหน้านั้นหายไป แล้วรอบนั้นจะถูกตัดสินเป็น no_data ทั้งที่ไม่ใช่
        """
        if db is None:
            with self.connect() as conn:
                return self.add_coverage(camera_id, entries, conn)
        totals = {}
        for round_key, seconds in entries:
            key = self._coverage_id(camera_id, round_key)
            try:
                current = float(self.get(self.COVERAGE_KIND, key, db)['seconds'])
            except KeyError:
                current = 0.0
            # หนึ่งรอบยาวหนึ่งชั่วโมง ยอดสะสมจึงเกิน 3600 ไม่ได้แม้จะส่งซ้ำ
            total = min(3600.0, current + float(seconds))
            self.put(self.COVERAGE_KIND,
                     {'id': key, 'camera_id': camera_id, 'round_key': round_key, 'seconds': total},
                     db)
            totals[round_key] = total
        return totals

    def coverage(self, camera_id, first_round_key, last_round_key):
        """ยอดเวลาที่กล้องเห็นภาพของทุกรอบในช่วง คืนเป็น dict ที่ summarise ใช้ได้ทันที"""
        lower = self._coverage_id(camera_id, first_round_key)
        upper = self._coverage_id(camera_id, last_round_key)
        with self.connect() as db:
            rows = db.execute(
                'SELECT data FROM records WHERE kind=? AND id>=? AND id<=?',
                (self.COVERAGE_KIND, lower, upper),
            ).fetchall()
        return {json.loads(row[0])['round_key']: float(json.loads(row[0])['seconds']) for row in rows}

    def inspection_payloads(self, start, end, camera_id=None):
        """payload ของรอบตรวจแม่เหล็กในช่วงเวลาที่ขอ เรียงตามเวลาที่เกิด

        คืน payload ที่บันทึกไว้ตอนนั้นตรง ๆ ไม่คำนวณใหม่ รายงานย้อนหลังจึงแสดง
        สิ่งที่ระบบตัดสินไว้ ณ เวลานั้นจริง ๆ ไม่ใช่ผลของกฎที่เพิ่งแก้เมื่อวาน
        """
        start = float(start); end = float(end)
        if not start < end:
            raise ValueError('invalid_time_range')
        if camera_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', camera_id):
            raise ValueError('invalid_camera_id')
        placeholders = ','.join('?' * len(self.INSPECTION_EVENT_TYPES))
        where = f'occurred_at>=? AND occurred_at<? AND event_type IN ({placeholders})'
        args = [start, end, *self.INSPECTION_EVENT_TYPES]
        if camera_id is not None:
            where += ' AND camera_id=?'; args.append(camera_id)
        with self.connect() as db:
            rows = db.execute(
                f'SELECT data FROM ai_events WHERE {where} ORDER BY occurred_at ASC', args
            ).fetchall()
        found = []
        for (data,) in rows:
            payload = json.loads(data).get('payload') or {}
            if 'round_key' in payload and 'completed_at' in payload:
                # รายงานใช้ชื่อ status ส่วนที่เก็บใช้ inspection_status ตามสเปคข้อ 15
                payload = dict(payload, status=payload.get('inspection_status'))
                found.append(payload)
        return found

    def review(self,key,revision,action,actor,boxes=None,negative=False):
        if action not in ('save','approve','reject') or not actor.strip() or len(actor)>100:
            raise ValueError('invalid_review')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            frame=self.get('frame',key,db)
            if frame['revision']!=revision:
                raise ValueError('revision_conflict_reload_frame')
            if boxes is not None:
                frame['boxes']=validate_boxes(boxes)
            if action=='approve' and not frame['boxes'] and not negative:
                raise ValueError('confirm_negative_image_first')
            frame['review_status']={'save':'pending','approve':'approved','reject':'rejected'}[action]
            frame['revision']+=1
            frame['reviewed_by']=actor
            frame['negative_confirmed']=bool(action=='approve' and not frame['boxes'] and negative)
            self.put('frame',frame,db)
            db.execute('INSERT INTO reviews(frame_id,revision,actor,action,data,created) VALUES (?,?,?,?,?,?)',
                       (key,frame['revision'],actor,action,json.dumps(frame),time.time()))
        return frame

    def stats(self):
        frames=self.list('frame')
        return dict(total=len(frames),pending=sum(f['review_status']=='pending' for f in frames),
                    approved=sum(f['review_status']=='approved' for f in frames),
                    rejected=sum(f['review_status']=='rejected' for f in frames),
                    boxes=sum(len(f['boxes']) for f in frames),
                    confirmed_negatives=sum(f.get('negative_confirmed',False) for f in frames),
                    groups=sorted({f['group_id'] for f in frames}))
