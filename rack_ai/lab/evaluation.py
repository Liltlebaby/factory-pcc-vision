"""Detection quality and counting quality are evaluated separately."""
from dataclasses import replace
import math
import cv2


def counting_error(expected,predicted):
    error=abs(expected-predicted)
    return dict(expected=expected,predicted=predicted,absolute_error=error,
                percentage_error=100*error/expected if expected else None,
                accuracy=max(0,1-error/expected) if expected else (1.0 if predicted==0 else 0.0),
                exact_match=expected==predicted)


def count_video(model_path,path,cfg):
    from rack_ai.detector import RackDetector
    from rack_ai.counter import RackCounter
    detector=RackDetector(replace(cfg,model=model_path));counter=RackCounter(cfg)
    cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS)
    total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not cap.isOpened() or not math.isfinite(fps) or fps<=0:cap.release();raise ValueError('benchmark_video_unreadable')
    stride=max(1,round(fps/cfg.inference_fps));index=0
    try:
        while True:
            ok=cap.grab()
            if not ok:break
            if index%stride==0:
                ok,frame=cap.retrieve()
                if not ok:raise ValueError('benchmark_decode_failed')
                counter.update(detector.infer(frame),frame.shape[0],index/fps)
            index+=1
    finally:cap.release()
    if not index:raise ValueError('empty_benchmark')
    if total>0 and index<total:raise ValueError('benchmark_decode_ended_early')
    return counter.count


def acceptance(candidate,baseline,counting):
    reasons=[]
    for key in ('precision','recall','map50'):
        if candidate[key]<.90:reasons.append(key+'_below_0.90')
    if candidate['recall']<baseline['recall']:reasons.append('recall_regression')
    if candidate['map5095']<baseline['map5095']:reasons.append('map5095_regression')
    if not counting:reasons.append('unseen_counting_benchmark_required')
    elif sum(x['candidate']['absolute_error'] for x in counting)>=sum(x['baseline']['absolute_error'] for x in counting):
        reasons.append('counting_not_better_on_unseen_clips')
    return dict(eligible=not reasons,reasons=reasons,automatic_promotion=False)
