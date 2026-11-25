"""Approved-only immutable dataset snapshots with clip/session isolation."""
import hashlib
import shutil
import time
import zipfile
from collections import Counter

import cv2
import yaml

from .store import identity,sha256,validate_boxes,yolo_text,atomic_json
from .duplicates import thumbnail,confirmed_duplicate


def build(store,assignments=None):
    frames=[f for f in store.list('frame') if f['review_status']=='approved']
    if not frames: raise ValueError('no_approved_images')
    groups=sorted({f['group_id'] for f in frames},key=lambda g:hashlib.sha256(g.encode()).hexdigest())
    if len(groups)<3: raise ValueError('need_at_least_three_independent_clips_or_sessions')
    if not assignments:
        n=len(groups);nt=max(1,round(n*.15));nv=max(1,round(n*.15))
        assignments={g:('test' if i<nt else 'val' if i<nt+nv else 'train') for i,g in enumerate(groups)}
    if set(assignments)!=set(groups) or set(assignments.values())!={'train','val','test'}:
        raise ValueError('assign_each_group_to_train_val_or_test')
    hashes={};sources={};signatures=[];issues=[];counts=Counter();areas=[];scores=[]
    hash_candidates_not_duplicates=0
    for frame in frames:
        split=assignments[frame['group_id']]
        path=store.path(frame['image_path']);image=cv2.imread(str(path))
        if image is None: issues.append('corrupted:'+frame['id']);continue
        if sha256(path)!=frame['image_sha256']:issues.append('changed_image:'+frame['id'])
        validate_boxes(frame['boxes'])
        if not frame['boxes'] and not frame.get('negative_confirmed'): issues.append('unconfirmed_negative:'+frame['id'])
        for mapping,key,label in ((hashes,frame['image_sha256'],'duplicate_image'),(sources,frame['source_hash'],'same_source_clip')):
            if key in mapping and mapping[key]!=split:issues.append(label+'_across_splits:'+frame['id'])
            mapping[key]=split
        sig=int(frame['signature'])
        small=thumbnail(image)
        for other,other_split,other_image,other_boxes,other_id in signatures:
            if other_split==split or (sig^other).bit_count()>3:continue
            if confirmed_duplicate(small,other_image,frame['boxes'],other_boxes):
                issues.append('near_duplicate_across_splits:'+frame['id']+':'+other_id)
            else:hash_candidates_not_duplicates+=1
        signatures.append((sig,split,small,frame['boxes'],frame['id']))
        counts[split]+=1;counts[split+'_boxes']+=len(frame['boxes'])
        counts['negative_images']+=int(not frame['boxes'])
        areas.extend((c-a)*(d-b) for a,b,c,d in frame['boxes']);scores.extend(frame.get('confidence',[]))
    if issues: raise ValueError('dataset_QC_failed: '+'; '.join(issues[:15]))
    if any(counts[s+'_boxes']==0 for s in ('train','val','test')):
        raise ValueError('each_split_needs_reviewed_rack_examples')
    key=identity('dataset');root=store.path('final/'+key);root.mkdir(parents=True,exist_ok=False)
    manifest=[]
    for frame in frames:
        split=assignments[frame['group_id']]
        image=root/'images'/split/(frame['id']+'.jpg');label=root/'labels'/split/(frame['id']+'.txt')
        image.parent.mkdir(parents=True,exist_ok=True);label.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(store.path(frame['image_path']),image)
        label.write_text(yolo_text(frame['boxes']),encoding='utf-8')
        manifest.append(dict(frame_id=frame['id'],clip_id=frame['clip_id'],group_id=frame['group_id'],
                             source_hash=frame['source_hash'],revision=frame['revision'],split=split,
                             image=str(image.relative_to(root)).replace('\\','/'),label=str(label.relative_to(root)).replace('\\','/'),
                             image_hash=sha256(image),label_hash=sha256(label)))
    config=dict(path=str(root).replace('\\','/'),train='images/train',val='images/val',test='images/test',names={0:'rack'})
    (root/'data.yaml').write_text(yaml.safe_dump(config,allow_unicode=True),encoding='utf-8')
    portable=dict(config,path='.')
    (root/'data_colab.yaml').write_text(yaml.safe_dump(portable,allow_unicode=True),encoding='utf-8')
    report=dict(total_images=len(frames),images_with_racks=len(frames)-counts['negative_images'],
                counts=dict(counts),total_boxes=sum(len(f['boxes']) for f in frames),
                average_boxes_per_image=sum(len(f['boxes']) for f in frames)/len(frames),
                duplicate_image_count=len(frames)-len(hashes),corrupted_image_count=0,missing_label_count=0,
                box_relative_areas=areas,auto_confidence_distribution=scores,
                duplicate_check='dhash_then_pixels_and_reviewed_regions_v2',
                hash_candidates_not_duplicates=hash_candidates_not_duplicates,
                note='Confidence values are machine suggestions, not review accuracy.')
    atomic_json(root/'manifest.json',manifest);atomic_json(root/'report.json',report)
    with zipfile.ZipFile(root/'dataset.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for item in manifest:
            archive.write(root/item['image'],item['image']);archive.write(root/item['label'],item['label'])
        archive.write(root/'data_colab.yaml','data.yaml')
        archive.write(root/'manifest.json','manifest.json');archive.write(root/'report.json','report.json')
    record=dict(id=key,created=time.time(),path=str(root.relative_to(store.root)),assignments=assignments,
                manifest_hash=sha256(root/'manifest.json'),config_hash=sha256(root/'data.yaml'),report=report,status='ready')
    store.put('dataset',record)
    return record


def verify_dataset(store,key):
    import json
    value=store.get('dataset',key);root=store.path(value['path'])
    if sha256(root/'manifest.json')!=value['manifest_hash']:raise ValueError('dataset_manifest_changed')
    if sha256(root/'data.yaml')!=value['config_hash']:raise ValueError('dataset_config_changed')
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    for item in manifest:
        for field in ('image','label'):
            path=(root/item[field]).resolve()
            if not path.is_relative_to(root) or sha256(path)!=item[field+'_hash']:
                raise ValueError('dataset_artifact_changed')
    return value,root,manifest
