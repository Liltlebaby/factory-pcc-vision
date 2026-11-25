"""Offline workers read finalized RAW clips, never the live capture object."""
import hashlib
import math
import time
from pathlib import Path

import cv2

from .store import atomic_json,sha256,yolo_text
from .selector import signature,assess


class AutoLabeler:
    def __init__(self,model_path,mode='yolo',reference=None):
        import torch
        from ultralytics import YOLO,YOLOE
        self.device=0 if torch.cuda.is_available() else 'cpu'
        torch.set_num_threads(2)
        if not Path(model_path).is_file(): raise ValueError('model_not_found')
        self.model=YOLO(str(model_path)) if mode=='yolo' else YOLOE(str(model_path))
        if mode=='yoloe':
            import numpy as np
            from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor
            if reference is None: raise ValueError('approved_visual_reference_required')
            path,box=reference
            self.model.predict(str(path),refer_image=str(path),visual_prompts={'bboxes':np.array([box],dtype=np.float32),'cls':np.array([0])},
                               predictor=YOLOEVPSegPredictor,device=self.device,verbose=False)

    def predict(self,frame):
        h,w=frame.shape[:2]
        result=self.model.predict(frame,conf=.10,iou=.7,imgsz=640,device=self.device,verbose=False)[0]
        boxes=[];scores=[]
        for box,score,cls in zip(result.boxes.xyxy.cpu().tolist(),result.boxes.conf.cpu().tolist(),result.boxes.cls.cpu().tolist()):
            if int(cls)!=0: continue
            a,b,c,d=box
            normalized=[max(0,a/w),max(0,b/h),min(1,c/w),min(1,d/h)]
            if normalized[0]<normalized[2] and normalized[1]<normalized[3]:
                boxes.append(normalized);scores.append(float(score))
        return boxes,scores


def extract(store,clips,clip_id,model_path,options,progress=lambda **kw:None,labeler=None):
    clip=clips.get(clip_id)
    if clip.get('raw') is not True or clip['status'] not in ('recorded','stopped'):
        raise ValueError('use_finalized_raw_recording_only')
    source=clips.file(clip_id,'raw')
    if 'annotated' in source.parts: raise ValueError('annotated_source_forbidden')
    source_hash=sha256(source)
    labeler=labeler or AutoLabeler(model_path)
    model_hash=sha256(model_path)
    cap=cv2.VideoCapture(str(source))
    if not cap.isOpened(): raise ValueError('clip_unreadable')
    source_fps=cap.get(cv2.CAP_PROP_FPS);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not math.isfinite(source_fps) or source_fps<=0:
        cap.release();raise ValueError('invalid_video_fps')
    sample_fps=float(options.get('sample_fps',1))
    stride=max(1,round(source_fps/sample_fps));limit=int(options.get('max_frames',300))
    start=float(options.get('start_seconds',0));duration=float(options.get('duration_seconds',900))
    first=round(start*source_fps);last=min(total,round((start+duration)*source_fps))
    if first>=last:
        cap.release();raise ValueError('empty_video_interval')
    cap.set(cv2.CAP_PROP_POS_FRAMES,first)
    seen=[];last_saved=-float('inf');light=None;count=None;saved=duplicates=0
    try:
        for index in range(first,last):
            if not cap.grab(): raise ValueError('video_decode_ended_early')
            if (index-first)%stride: continue
            ok,frame=cap.retrieve()
            if not ok: raise ValueError('video_frame_unreadable')
            second=index/source_fps
            boxes,scores=labeler.predict(frame)
            quality=assess(frame,boxes,scores,light,count)
            light=quality['brightness'];count=len(boxes)
            code=signature(frame)
            # Always allow a diversity sample every 30s; time overlays can fool hashes.
            if any((code^old).bit_count()<=3 for old in seen[-120:]) and second-last_saved<30:
                duplicates+=1;continue
            if quality['priority']=='LOW_VALUE' and second-last_saved<5: continue
            key='frame_'+hashlib.sha256(f'{source_hash}:{index}'.encode()).hexdigest()[:32]
            try:
                store.get('frame',key)
                continue  # extraction reruns never overwrite a human review
            except KeyError: pass
            relative=f'candidate/images/{key}.jpg';path=store.path(relative)
            path.parent.mkdir(parents=True,exist_ok=True)
            if not cv2.imwrite(str(path),frame,[cv2.IMWRITE_JPEG_QUALITY,95]): raise OSError('image_write_failed')
            label_path=store.path(f'candidate/labels/{key}.txt');label_path.parent.mkdir(parents=True,exist_ok=True)
            label_path.write_text(yolo_text(boxes),encoding='utf-8')
            value=dict(id=key,clip_id=clip_id,group_id=clip.get('session_id') or clip_id,
                source_hash=source_hash,frame_index=index,second=second,image_path=relative,
                image_sha256=sha256(path),signature=str(code),width=frame.shape[1],height=frame.shape[0],
                boxes=boxes,auto_boxes=boxes,confidence=scores,model_sha256=model_hash,
                review_status='pending',revision=0,negative_confirmed=False,created=time.time(),**quality)
            store.put('frame',value)
            atomic_json(store.path(f'candidate/metadata/{key}.json'),value)
            seen.append(code);last_saved=second;saved+=1
            progress(saved=saved,duplicates_skipped=duplicates,video_seconds=round(second,2))
            if saved>=limit:break
    finally:
        cap.release()
    progress(saved=saved,duplicates_skipped=duplicates,stage='completed')
    return dict(saved=saved,duplicates_skipped=duplicates,source_hash=source_hash)
