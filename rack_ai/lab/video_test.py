"""Offline annotated-video test using the same detector and counter as live."""
import csv
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import cv2

from rack_ai.counter import RackCounter
from rack_ai.preview_filter import select_preview_tracks
from .store import atomic_json,identity,sha256


def resolve_model(store,cfg,model_id):
    if model_id=='current':return cfg.model,'current',sha256(cfg.model)
    record=store.get('model',model_id)
    if record['status'] not in ('trained','evaluated'):raise ValueError('model_not_ready')
    path=store.path(record['path'])/'best.pt'
    if not path.is_file() or sha256(path)!=record['sha256']:raise ValueError('model_changed')
    return path,record['id'],record['sha256']


def analyze(store,clips,cfg,options,progress=lambda **kw:None,detector=None,web_encode=True):
    from rack_ai.detector import RackDetector
    clip=clips.get(options['clip_id'])
    if not clip.get('raw') or clip['status'] not in ('recorded','stopped'):raise ValueError('finalized_raw_clip_required')
    source=clips.file(clip['clip_id'],'raw');model_path,model_id,model_hash=resolve_model(store,cfg,options['model_id'])
    detector=detector or RackDetector(replace(cfg,model=model_path));counter=RackCounter(cfg)
    capture=cv2.VideoCapture(str(source))
    if not capture.isOpened():raise ValueError('video_unreadable')
    fps=float(capture.get(cv2.CAP_PROP_FPS));total=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps<=0 or total<=0 or width<=0 or height<=0:raise ValueError('video_metadata_invalid')
    sample_fps=float(options.get('sample_fps',5));stride=max(1,round(fps/sample_fps));output_fps=fps/stride
    first=round(float(options.get('start_seconds',0))*fps)
    last=min(total,round((float(options.get('start_seconds',0))+float(options.get('duration_seconds',600)))*fps))
    if first>=last:raise ValueError('empty_video_interval')
    key=identity('video_test');root=store.path('video_tests/'+key);root.mkdir(parents=True,exist_ok=False)
    working=root/'working.mp4';result_path=root/'result.mp4';csv_path=root/'events.csv'
    writer=cv2.VideoWriter(str(working),cv2.VideoWriter_fourcc(*'mp4v'),output_fps,(width,height))
    if not writer.isOpened():capture.release();raise ValueError('video_writer_unavailable')
    capture.set(cv2.CAP_PROP_POS_FRAMES,first);events=[];processed=0;started=time.time()
    suppressed_detections=0;suppressed_frames=0
    try:
        for index in range(first,last):
            if not capture.grab():break
            if (index-first)%stride:continue
            ok,frame=capture.retrieve()
            if not ok:raise ValueError('video_decode_failed')
            second=index/fps;before=counter.count;tracks=counter.update(detector.infer(frame),height,second)
            if counter.count!=before:
                event=dict(counter.last_event,video_second=second);events.append(event)
            cv2.line(frame,(0,int(height*cfg.line)),(width,int(height*cfg.line)),(255,0,255),3)
            visible_tracks=select_preview_tracks(tracks,height*cfg.line)
            suppressed=len(tracks)-len(visible_tracks)
            suppressed_detections+=suppressed
            suppressed_frames+=int(suppressed>0)
            for track in visible_tracks:
                x1,y1,x2,y2=(int(v) for v in track['bbox']);color=(0,0,255) if track['counted'] else (0,220,0)
                cv2.rectangle(frame,(x1,y1),(x2,y2),color,3)
                cv2.putText(frame,f"rack ID:{track['track_id']} {track['confidence']:.2f}",(x1,max(28,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,.75,color,2)
            cv2.putText(frame,f'RACK OUT: {counter.count}',(24,45),cv2.FONT_HERSHEY_SIMPLEX,1.15,(0,255,255),3)
            cv2.putText(frame,f'{second:.1f}s | {model_id}',(24,78),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,255,255),2)
            writer.write(frame);processed+=1
            if processed%10==0:progress(stage='analyzing',frames=processed,total_frames=(last-first+stride-1)//stride,count=counter.count)
    finally:writer.release();capture.release()
    if not processed:raise ValueError('no_frames_processed')
    codec='mp4v'
    ffmpeg=shutil.which('ffmpeg') if web_encode else None
    if ffmpeg:
        command=[ffmpeg,'-y','-loglevel','error','-i',str(working),'-an','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(result_path)]
        completed=subprocess.run(command,capture_output=True,timeout=max(120,int(processed/output_fps)*2))
        if completed.returncode:raise ValueError('web_video_encode_failed')
        working.unlink();codec='h264'
    else:working.replace(result_path)
    with csv_path.open('w',newline='',encoding='utf-8-sig') as output:
        writer_csv=csv.DictWriter(output,fieldnames=['rack_number','track_id','video_second','confidence'])
        writer_csv.writeheader()
        for event in events:writer_csv.writerow(dict(rack_number=event['rackNumber'],track_id=event['trackId'],video_second=round(event['video_second'],3),confidence=event['confidence']))
    record=dict(id=key,status='completed',created=time.time(),clip_id=clip['clip_id'],clip_sha256=sha256(source),
                model_id=model_id,model_sha256=model_hash,count=counter.count,events=len(events),frames=processed,
                start_seconds=float(options.get('start_seconds',0)),duration_seconds=processed/output_fps,
                output_fps=output_fps,codec=codec,elapsed_seconds=time.time()-started,
                preview_suppressed_detections=suppressed_detections,
                preview_suppressed_frames=suppressed_frames,
                video_path=str(result_path.relative_to(store.root)),csv_path=str(csv_path.relative_to(store.root)))
    atomic_json(root/'report.json',record);store.put('video_test',record)
    progress(stage='completed',frames=processed,count=counter.count,video_test_id=key)
    return record
