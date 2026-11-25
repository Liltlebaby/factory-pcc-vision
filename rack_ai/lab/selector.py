"""Heuristic review priority, not a claim that an object is a false positive."""
import cv2
import numpy as np


def signature(frame):
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    small=cv2.resize(gray,(9,8),interpolation=cv2.INTER_AREA)
    bits=(small[:,1:]>small[:,:-1]).flatten()
    return sum(int(bit)<<i for i,bit in enumerate(bits))


def overlap(a,b):
    x1,y1,x2,y2=a;u1,v1,u2,v2=b
    inter=max(0,min(x2,u2)-max(x1,u1))*max(0,min(y2,v2)-max(y1,v1))
    return inter/max(1e-9,(x2-x1)*(y2-y1)+(u2-u1)*(v2-v1)-inter)


def assess(frame,boxes,scores,previous=None,previous_count=None):
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    light=float(gray.mean());blur=float(cv2.Laplacian(gray,cv2.CV_64F).var())
    reasons=[]
    if any(.25<=score<=.70 for score in scores): reasons.append('uncertain_detection')
    if any(score<.25 for score in scores): reasons.append('very_low_confidence_candidate')
    if any(overlap(a,b)>.2 for i,a in enumerate(boxes) for b in boxes[i+1:]): reasons.append('overlap')
    if len(boxes)>1: reasons.append('multiple_racks')
    if any((c-a)*(d-b)<.005 or (c-a)*(d-b)>.55 for a,b,c,d in boxes): reasons.append('unusual_box_size')
    if any(min(a,b,1-c,1-d)<.03 for a,b,c,d in boxes): reasons.append('edge_object')
    if light<45 or light>210: reasons.append('lighting')
    if blur<50: reasons.append('blur')
    if previous is not None and abs(light-previous)>20: reasons.append('lighting_change')
    if previous_count is not None and previous_count!=len(boxes): reasons.append('object_count_change')
    if not boxes: reasons.append('possible_negative_or_missed_rack')
    high=any(r in reasons for r in ('uncertain_detection','very_low_confidence_candidate','overlap','lighting','lighting_change','object_count_change','edge_object','unusual_box_size'))
    priority='HIGH_VALUE' if high else 'MEDIUM_VALUE' if reasons or any(s<.9 for s in scores) else 'LOW_VALUE'
    return dict(priority=priority,reasons=reasons or ['scene_diversity'],brightness=light,blur=blur)
