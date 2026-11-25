"""Persistent one-shot schedules and opt-in event recording; no capture calls."""
import json
import logging
import threading
import time
import uuid

log = logging.getLogger('rack.recording_control')
DEFAULT_POLICY = dict(enabled=False,duration_minutes=10,cooldown_seconds=900,
                      low_confidence=True,multiple_racks=True,rack_exit=False,annotated=False)


class RecordingControl:
    def __init__(self, recorder, provider):
        self.recorder, self.provider = recorder, provider
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run,name='recording-control',daemon=True)
        self.lock = threading.RLock()
        self.initialized = False
        self.last_frame = -1
        self.last_count = None
        self.error = None

    def initialize(self):
        with self.lock:
            if self.initialized:
                return
            store = self.recorder.storage()
            with store.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS recording_jobs (id TEXT PRIMARY KEY, due REAL NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL)')
                db.execute('CREATE INDEX IF NOT EXISTS idx_recording_jobs_due ON recording_jobs(status,due)')
                db.execute('CREATE TABLE IF NOT EXISTS recording_settings (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
                db.execute("UPDATE recording_jobs SET status='interrupted' WHERE status='dispatching'")
            self.initialized = True

    def start(self):
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=10)

    def policy(self):
        self.initialize()
        with self.recorder.storage().connect() as db:
            row = db.execute("SELECT data FROM recording_settings WHERE id='event_policy'").fetchone()
        return json.loads(row[0]) if row else dict(DEFAULT_POLICY)

    def set_policy(self, value):
        self.initialize()
        with self.recorder.storage().connect() as db:
            db.execute("INSERT OR REPLACE INTO recording_settings VALUES ('event_policy',?)",(json.dumps(value),))
        return value

    def add(self, due, options):
        self.initialize()
        if not time.time() < due <= time.time()+366*86400:
            raise ValueError('schedule_must_be_in_next_year')
        identity = 'schedule_'+uuid.uuid4().hex
        with self.recorder.storage().connect() as db:
            db.execute('INSERT INTO recording_jobs VALUES (?,?,?,?)',(identity,due,'pending',json.dumps(options)))
        return dict(id=identity,due=due,status='pending',**options)

    def jobs(self):
        self.initialize()
        with self.recorder.storage().connect() as db:
            return [dict(id=r[0],due=r[1],status=r[2],**json.loads(r[3]))
                    for r in db.execute('SELECT id,due,status,data FROM recording_jobs ORDER BY due DESC LIMIT 500')]

    def cancel(self, identity):
        self.initialize()
        with self.recorder.storage().connect() as db:
            changed = db.execute("UPDATE recording_jobs SET status='cancelled' WHERE id=? AND status='pending'",(identity,)).rowcount
        if not changed:
            raise ValueError('schedule_not_pending')

    def tick(self, now=None):
        self.initialize()
        now = time.time() if now is None else now
        store = self.recorder.storage()
        with store.connect() as db:
            rows = db.execute("SELECT id,due,data FROM recording_jobs WHERE status='pending' AND due<=? ORDER BY due LIMIT 20",(now,)).fetchall()
        for identity,due,data in rows:
            status = 'missed' if now-due > 60 else 'skipped_busy' if self.recorder.snapshot()['active'] else 'dispatching'
            with store.connect() as db:
                claimed = db.execute("UPDATE recording_jobs SET status=? WHERE id=? AND status='pending'",(status,identity)).rowcount
            if not claimed or status != 'dispatching':
                continue
            options = json.loads(data)
            try:
                result = self.recorder.start(options['duration_minutes'],options['name'],options.get('annotated',False),source='scheduled')
                options['clip_id'] = result['clip_id']
                status = 'dispatched'
            except Exception as exc:
                status = 'failed'
                options['error'] = type(exc).__name__
            with store.connect() as db:
                db.execute('UPDATE recording_jobs SET status=?,data=? WHERE id=?',(status,json.dumps(options),identity))

        policy = self.policy()
        state,_ = self.provider()
        count = state.get('rack_count',0)
        exited = self.last_count is not None and count > self.last_count
        self.last_count = count
        if state.get('frame_id',-1) == self.last_frame:
            return
        self.last_frame = state.get('frame_id',-1)
        if not policy['enabled'] or self.recorder.snapshot()['active'] or time.monotonic()-state.get('_monotonic',0) > 5:
            return
        tracks = state.get('tracks',[])
        reason = ('rack_exit' if policy['rack_exit'] and exited else
                  'low_confidence' if policy['low_confidence'] and any(.25 <= t['confidence'] <= .7 for t in tracks) else
                  'multiple_racks' if policy['multiple_racks'] and len(tracks)>=2 else None)
        if not reason:
            return
        with store.connect() as db:
            row = db.execute("SELECT data FROM recording_settings WHERE id='event_last_attempt'").fetchone()
            if row and now-float(row[0]) < policy['cooldown_seconds']:
                return
            db.execute("INSERT OR REPLACE INTO recording_settings VALUES ('event_last_attempt',?)",(str(now),))
        self.recorder.start(policy['duration_minutes'],'event_'+reason,policy['annotated'],source='event')

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
                self.error = None
            except Exception as exc:
                self.error = type(exc).__name__
                log.warning('recording_control_error type=%s',self.error)
            self.stop_event.wait(1)
