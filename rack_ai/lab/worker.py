import argparse
import time
from pathlib import Path

from rack_ai.config import Settings
from rack_ai.recording import ClipStore
from .store import LabStore


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--job',required=True)
    args=parser.parse_args();store=LabStore(args.root);job=store.get('job',args.job)
    cfg=dict(job['config'])  # keep stored JSON config separate from runtime Path objects
    for key in ('model','record_root','lab_root','yoloe_model'):cfg[key]=Path(cfg[key])
    cfg=Settings(**cfg);job.update(status='running',started=time.time());store.put('job',job)
    def progress(**value):
        job['progress']=value;store.put('job',job)
    try:
        clips=ClipStore(cfg.record_root)
        if job['type']=='extract':
            from .extractor import extract,AutoLabeler
            options=job['options'];labeler=None
            if options.get('labeler')=='yoloe':
                ref=store.get('frame',options['reference_id'])
                if ref['review_status']!='approved' or not ref['boxes']:raise ValueError('approved_rack_reference_required')
                a,b,c,d=ref['boxes'][0]
                labeler=AutoLabeler(cfg.yoloe_model,'yoloe',(store.path(ref['image_path']),[a*ref['width'],b*ref['height'],c*ref['width'],d*ref['height']]))
            job['result']=extract(store,clips,options['clip_id'],cfg.yoloe_model if labeler else cfg.model,options,progress,labeler)
        elif job['type']=='build':
            from .builder import build
            job['result']=build(store,job['options'].get('assignments'))
        elif job['type']=='train':
            from .training import train
            job['result']=train(store,cfg,job['options'],progress)
        elif job['type']=='evaluate':
            from .training import evaluate
            job['result']=evaluate(store,clips,cfg,job['options'],progress)
        else:
            from .video_test import analyze
            job['result']=analyze(store,clips,cfg,job['options'],progress)
        job['status']='completed'
    except Exception as exc:
        job.update(status='failed',error=str(exc)[:1000] if isinstance(exc,ValueError) else type(exc).__name__)
    job['finished']=time.time();store.put('job',job)


if __name__=='__main__':main()
