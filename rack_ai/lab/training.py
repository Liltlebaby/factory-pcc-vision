"""Versioned training; no mutation of the currently deployed weights."""
import json
import shutil
import time
from pathlib import Path

from .builder import verify_dataset
from .store import identity,sha256,atomic_json
from .evaluation import count_video,counting_error,acceptance


def metrics(result):
    output=dict(precision=float(result.box.mp),recall=float(result.box.mr),
                map50=float(result.box.map50),map5095=float(result.box.map))
    matrix=getattr(getattr(result,'confusion_matrix',None),'matrix',None)
    output.update(false_positives=float(matrix[:-1,-1].sum()) if matrix is not None else None,
                  false_negatives=float(matrix[-1,:-1].sum()) if matrix is not None else None,
                  note='Precision/recall at max-F1; confusion matrix FP/FN use validator threshold.')
    return output


def train(store,cfg,options,progress=lambda **kw:None):
    import torch
    from ultralytics import YOLO
    dataset,root,manifest=verify_dataset(store,options['dataset_id'])
    torch.set_num_threads(2);device=0 if torch.cuda.is_available() else 'cpu'
    version=identity('model');destination=store.path('models/'+version);destination.mkdir(parents=True,exist_ok=False)
    baseline_hash=sha256(cfg.model)
    # Retain the exact comparison weights even after a later manual deployment.
    shutil.copy2(cfg.model,destination/'baseline.pt')
    if sha256(destination/'baseline.pt')!=baseline_hash:raise ValueError('baseline_changed_during_copy')
    record=dict(id=version,display_name=options.get('name') or version,status='training',created=time.time(),dataset_id=dataset['id'],baseline_sha256=baseline_hash,
                path=str(destination.relative_to(store.root)),options=options)
    store.put('model',record)
    try:
        model=YOLO(str(destination/'baseline.pt'))
        model.add_callback('on_fit_epoch_end',lambda trainer:progress(epoch=int(trainer.epoch)+1,total_epochs=options['epochs'],model_id=version))
        model.train(data=str(root/'data.yaml'),epochs=options.get('epochs',100),imgsz=options.get('imgsz',640),
                    batch=options.get('batch',4),device=device,workers=0,cache=False,plots=False,
                    project=str(destination),name='training',exist_ok=False,patience=20,
                    degrees=2,translate=.08,scale=.3,perspective=.0005,hsv_v=.35,fliplr=0.0)
        source=Path(model.trainer.save_dir)/'weights/best.pt'
        shutil.copy2(source,destination/'best.pt')
        record.update(status='trained',sha256=sha256(destination/'best.pt'))
        store.put('model',record)
        return record
    except BaseException:
        record['status']='failed';store.put('model',record);raise


def evaluate(store,clips,cfg,options,progress=lambda **kw:None):
    from ultralytics import YOLO
    import torch
    record=store.get('model',options['model_id'])
    if record['status'] not in ('trained','evaluated'):raise ValueError('model_not_trained')
    _,root,manifest=verify_dataset(store,record['dataset_id'])
    destination=store.path(record['path']);path=destination/'best.pt'
    if sha256(path)!=record['sha256']:raise ValueError('model_changed')
    baseline_path=destination/'baseline.pt'
    if sha256(baseline_path)!=record['baseline_sha256']:raise ValueError('baseline_snapshot_changed')
    torch.set_num_threads(2);device=0 if torch.cuda.is_available() else 'cpu'
    tag=identity('evaluation');output=destination/tag
    candidate=metrics(YOLO(str(path)).val(data=str(root/'data.yaml'),split='test',device=device,workers=0,plots=True,project=str(output),name='candidate'))
    progress(stage='evaluate_baseline')
    baseline=metrics(YOLO(str(baseline_path)).val(data=str(root/'data.yaml'),split='test',device=device,workers=0,plots=True,project=str(output),name='baseline'))
    used_sources={item['source_hash'] for item in manifest}  # benchmark must be outside all dataset splits
    counting=[]
    for key in options.get('benchmark_ids',[]):
        benchmark=store.get('benchmark',key);clip=clips.get(benchmark['clip_id'])
        if not clip.get('raw') or clip['status'] not in ('recorded','stopped'):raise ValueError('benchmark_not_finalized_raw')
        video=clips.file(benchmark['clip_id'],'raw');digest=sha256(video)
        if digest!=benchmark['source_hash'] or digest in used_sources:raise ValueError('benchmark_changed_or_not_unseen')
        progress(stage='counting',benchmark_id=key)
        counting.append(dict(benchmark_id=key,baseline=counting_error(benchmark['expected_count'],count_video(baseline_path,video,cfg)),
                             candidate=counting_error(benchmark['expected_count'],count_video(path,video,cfg))))
    result=dict(candidate=candidate,baseline=baseline,counting=counting,decision=acceptance(candidate,baseline,counting))
    atomic_json(output/'comparison.json',result)
    record.update(status='evaluated',evaluation=result,evaluated_at=time.time())
    store.put('model',record)
    return result
