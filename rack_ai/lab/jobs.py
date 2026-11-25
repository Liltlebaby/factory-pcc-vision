"""Heavy jobs run in an isolated process with a single-job admission limit."""
import json
import subprocess
import sys
import threading
import time
import os
from dataclasses import asdict
from pathlib import Path

from .store import LabStore,identity


class LabManager:
    def __init__(self,cfg):
        self.cfg=cfg
        self.store=LabStore(cfg.lab_root)
        self.lock=threading.Lock();self.process=None;self.job_id=None;self.log=None

    def recover(self):
        for job in self.store.list('job'):
            if job['status'] in ('queued','running'):
                job.update(status='interrupted',error='service_restarted');self.store.put('job',job)
        for model in self.store.list('model'):
            if model['status']=='training':
                model['status']='interrupted';self.store.put('model',model)

    def refresh(self):
        if self.process is not None and self.process.poll() is not None:
            job=self.store.get('job',self.job_id)
            if job['status'] in ('queued','running'):
                job.update(status='failed',error='worker_exited');self.store.put('job',job)
            if self.log:self.log.close()
            self.process=None;self.log=None

    def submit(self,kind,options):
        if kind not in ('extract','build','train','evaluate','video_test'):raise ValueError('invalid_job_type')
        with self.lock:
            self.refresh()
            if self.process is not None:raise ValueError('heavy_job_already_running')
            key=identity('job')
            config=asdict(self.cfg)
            for field,value in config.items():
                if isinstance(value,Path):config[field]=str(value.resolve())
            # Workers do not need camera credentials or API tokens.
            config.update(source='',record_source='',token='')
            job=dict(id=key,type=kind,options=options,config=config,status='queued',created=time.time(),progress={})
            self.store.put('job',job)
            logs=self.store.path('logs');logs.mkdir(exist_ok=True)
            self.log=(logs/(key+'.log')).open('ab')
            try:
                self.process=subprocess.Popen([sys.executable,'-m','rack_ai.lab.worker','--root',str(self.store.root),'--job',key],
                    cwd=str(Path(__file__).resolve().parents[2]),stdout=self.log,stderr=self.log,
                    env={k:v for k,v in os.environ.items() if k not in ('CAMERA_SOURCE','CAMERA_RTSP_AI','CAMERA_RTSP_RECORD','RACK_API_TOKEN')},
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
                self.job_id=key
            except Exception:
                self.log.close();self.log=None
                job.update(status='failed',error='worker_start_failed');self.store.put('job',job);raise
            return self.public(job)

    @staticmethod
    def public(job):
        return {k:v for k,v in job.items() if k!='config'}

    def status(self):
        with self.lock:
            self.refresh()
            return [self.public(j) for j in self.store.list('job')[:50]]

    def cancel(self,key):
        with self.lock:
            self.refresh()
            if self.process is None or key!=self.job_id:raise ValueError('job_not_running')
            self.process.terminate()
            try:self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            job=self.store.get('job',key);job.update(status='cancelled',finished=time.time())
            self.store.put('job',job)
            self.refresh()
            for model in self.store.list('model'):
                if model['status']=='training':model['status']='interrupted';self.store.put('model',model)
            return self.public(job)

    def close(self):
        if self.process is not None:
            try:self.cancel(self.job_id)
            except ValueError:pass
