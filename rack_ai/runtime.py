"""Local service safeguards: single instance and durable count snapshots."""
import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .lab.store import LabStore


class InstanceLock:
    def __init__(self,root):self.path=Path(root)/'.service.lock';self.file=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a+b')
        try:
            if self.path.stat().st_size==0:
                self.file.write(b'0');self.file.flush()
            self.file.seek(0)
            import msvcrt
            msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except ImportError:
            import fcntl
            fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close();raise RuntimeError('Rack Monitor already running for this recording directory')
        return self
    def __exit__(self,*args):
        if self.file:self.file.close()


class CountJournal:
    """Persist every count event and its latest counter without blocking inference."""
    def __init__(self,root):
        self.root=Path(root);self.store=None;self.pending=queue.Queue()
        self.stop=threading.Event();self.error=None
        self.thread=threading.Thread(target=self._run,name='count-journal',daemon=True)
    def start(self):
        value=0
        try:
            self.store=LabStore(self.root)
            try:value=self.store.get('counter','Camera09')['count']
            except KeyError:pass
        except Exception:self.error='counter_storage_unavailable'
        self.thread.start();return value
    def submit(self,count,event):
        value=dict(id='Camera09',count=count,last_event=event,updated=time.time())
        self.pending.put_nowait(value)
    @staticmethod
    def _event(value):
        event=value.get('last_event')
        if not event:return None
        timestamp=float(event['timestamp'])
        # นับ "เก๊ะ" ที่ออกจากหอโรยยางก่อนเข้าเตา — ชื่อ rubber_* เดิมถูกเลิกใช้
        # เพื่อกันไว้ให้เซ็นเซอร์นับก้อนยางก่อนแพ็คที่จะเพิ่มเข้ามาภายหลัง
        event_id=f"camera-09:rack-counting:{int(timestamp*1_000_000)}:{int(event['trackId'])}:{int(event['rackNumber'])}"
        return dict(event_id=event_id,camera_id='camera-09',task_id='rack-counting',
                    station_id='rack-infeed',type='rack_counted',
                    occurred_at=datetime.fromtimestamp(timestamp,timezone.utc).isoformat().replace('+00:00','Z'),
                    model_version=event.get('model_version'),model_sha256=event.get('model_sha256'),
                    rule_version=event.get('rule_version','rack-count-v1'),
                    payload=dict(rack_count=int(event['rackNumber']),track_id=int(event['trackId']),
                                 confidence=float(event['confidence'])))
    def _run(self):
        retry=None
        while not self.stop.is_set() or not self.pending.empty():
            try:retry=self.pending.get(timeout=.2)
            except queue.Empty:
                if retry is None:continue
            try:
                self.store=self.store or LabStore(self.root)
                with self.store.connect() as db:
                    self.store.put('counter',retry,db)
                    event=self._event(retry)
                    if event:self.store.append_event(event,db)
                self.error=None;retry=None
            except Exception:
                self.error='counter_save_failed'
                if self.stop.wait(1):break
    def close(self):self.stop.set();self.thread.join(timeout=5)
    def count_times(self,start,end,station_id=None):
        self.store=self.store or LabStore(self.root)
        return self.store.count_times(start,end,station_id=station_id)
    def events(self,after=0,limit=100,station_id=None):
        self.store=self.store or LabStore(self.root)
        return self.store.events(after=after,limit=limit,station_id=station_id)
    def ingest(self,camera_id,events,coverage=()):
        """บันทึกเหตุการณ์จาก worker ภายนอกพร้อมเวลาที่กล้องเห็นภาพ ในทรานแซกชันเดียว

        เขียนตรงไม่ผ่านคิวเหมือนตัวนับเก๊ะ เพราะฝั่งที่เรียกเป็น HTTP ที่รอคำตอบอยู่
        ถ้าเขียนไม่สำเร็จ worker ต้องรู้เพื่อส่งใหม่ ไม่ใช่ได้ 200 แล้วข้อมูลหายไปเฉย ๆ
        """
        self.store=self.store or LabStore(self.root)
        with self.store.connect() as db:
            cursors=[self.store.append_event(event,db) for event in events]
            totals=self.store.add_coverage(camera_id,coverage,db) if coverage else {}
        return dict(stored=len(cursors),cursors=cursors,coverage=totals)
    def inspection_payloads(self,start,end,camera_id=None):
        self.store=self.store or LabStore(self.root)
        return self.store.inspection_payloads(start,end,camera_id=camera_id)
    def coverage(self,camera_id,first_round_key,last_round_key):
        self.store=self.store or LabStore(self.root)
        return self.store.coverage(camera_id,first_round_key,last_round_key)


class JsonFormatter(logging.Formatter):
    def format(self,record):
        return json.dumps(dict(time=time.time(),level=record.levelname,logger=record.name,message=record.getMessage()),ensure_ascii=False)
