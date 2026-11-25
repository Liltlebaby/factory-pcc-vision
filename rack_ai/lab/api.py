from pathlib import Path
from typing import Literal

from fastapi import APIRouter,HTTPException,Query,Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel,Field

from .store import sha256,identity


class ExtractRequest(BaseModel):
    sample_fps: float=Field(1,ge=.1,le=3,allow_inf_nan=False)
    max_frames: int=Field(300,ge=1,le=2000)
    start_seconds: float=Field(0,ge=0,allow_inf_nan=False)
    duration_seconds: float=Field(900,gt=0,le=3600,allow_inf_nan=False)
    labeler: Literal['yolo','yoloe']='yolo'
    reference_id: str|None=None


class ReviewRequest(BaseModel):
    revision: int=Field(ge=0)
    actor: str=Field(min_length=1,max_length=100)
    boxes: list[list[float]]|None=None
    negative_confirmed: bool=False


class BuildRequest(BaseModel):
    assignments: dict[str,Literal['train','val','test']]|None=None


class TrainRequest(BaseModel):
    dataset_id: str
    name: str=Field('Rack model',min_length=1,max_length=80,pattern=r'^[\w .()\-]+$')
    epochs: int=Field(100,ge=1,le=300)
    imgsz: int=Field(640,ge=64,le=1280,multiple_of=32)
    batch: int=Field(4,ge=1,le=32)


class EvaluateRequest(BaseModel):
    model_id: str
    benchmark_ids: list[str]=Field(default_factory=list,max_length=20)


class BenchmarkRequest(BaseModel):
    clip_id: str
    expected_count: int=Field(ge=0,le=100000)
    actor: str=Field(min_length=1,max_length=100)

class VideoTestRequest(BaseModel):
    clip_id: str
    model_id: str='current'
    start_seconds: float=Field(0,ge=0,allow_inf_nan=False)
    duration_seconds: float=Field(600,gt=0,le=3600,allow_inf_nan=False)
    sample_fps: float=Field(5,ge=1,le=10,allow_inf_nan=False)


class ModelNameRequest(BaseModel):
    name: str=Field(min_length=1,max_length=80,pattern=r'^[\w .()\-]+$')


def router(manager,clips):
    route=APIRouter()
    def attempt(fn):
        try:return fn()
        except KeyError:raise HTTPException(404,'item_not_found')
        except ValueError as exc:raise HTTPException(409,str(exc))
        except (OSError,):raise HTTPException(503,'storage_unavailable')

    @route.get('/dataset')
    def page():return FileResponse(Path(__file__).parents[1]/'frontend/dataset.html')

    @route.get('/dataset.js')
    def script():return FileResponse(Path(__file__).parents[1]/'frontend/dataset.js',media_type='text/javascript')

    @route.post('/api/dataset/extract/{clip_id}')
    def extract(clip_id:str,body:ExtractRequest):
        def run():
            clip=clips().get(clip_id)
            if clip.get('raw') is not True or clip['status'] not in ('recorded','stopped'):raise ValueError('finalized_raw_clip_required')
            return manager().submit('extract',dict(clip_id=clip_id,**body.model_dump()))
        return attempt(run)

    @route.post('/api/recordings/upload')
    async def upload(request:Request,filename:str=Query(min_length=1,max_length=255)):
        """Raw request body avoids buffering multi-GB CCTV files or requiring multipart."""
        from .importer import ensure_upload_capacity,finalize_upload,MAX_UPLOAD_BYTES,clean_name
        store=clips();temp=None
        try:
            clean_name(filename)
            length=request.headers.get('content-length')
            ensure_upload_capacity(store.root,int(length) if length and length.isdigit() else None)
            temp=store.root/'raw'/('.upload_'+identity('part'))
            size=0
            with temp.open('xb') as output:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>MAX_UPLOAD_BYTES:raise ValueError('upload_exceeds_5GB')
                    output.write(chunk)
            return finalize_upload(store,temp,filename,size)
        except KeyError:raise HTTPException(404,'item_not_found')
        except ValueError as exc:raise HTTPException(409,str(exc))
        except OSError:raise HTTPException(503,'upload_storage_unavailable')
        finally:
            if temp is not None and temp.exists():temp.unlink()

    @route.get('/api/dataset/candidates')
    def candidates(status:Literal['pending','approved','rejected','all']='pending',offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
        items=manager().store.list('frame')
        items=[f for f in items if status=='all' or f['review_status']==status]
        rank={'HIGH_VALUE':0,'MEDIUM_VALUE':1,'LOW_VALUE':2}
        items.sort(key=lambda f:(rank[f['priority']],f['clip_id'],f['second']))
        return dict(total=len(items),items=items[offset:offset+limit])

    @route.get('/api/dataset/stats')
    def stats():return manager().store.stats()

    @route.get('/api/dataset/review/{key}')
    def frame(key:str):return attempt(lambda:manager().store.get('frame',key))

    @route.get('/api/dataset/image/{key}')
    def image(key:str):
        def get():
            store=manager().store;f=store.get('frame',key)
            return FileResponse(store.path(f['image_path']),media_type='image/jpeg',headers={'Cache-Control':'no-store'})
        return attempt(get)

    @route.post('/api/dataset/review/{key}/{action}')
    def review(key:str,action:Literal['approve','reject','annotations'],body:ReviewRequest):
        return attempt(lambda:manager().store.review(key,body.revision,'save' if action=='annotations' else action,body.actor,body.boxes,body.negative_confirmed))

    @route.get('/api/roboflow/export')
    def roboflow_export(status:Literal['pending','approved','all']='pending'):
        def get():
            from .roboflow import export_zip
            path,count=export_zip(manager().store,status)
            return FileResponse(path,filename=f'rack_roboflow_{status}_{count}_images.zip',media_type='application/zip',
                                background=BackgroundTask(path.unlink,missing_ok=True))
        return attempt(get)

    @route.post('/api/roboflow/import')
    async def roboflow_import(request:Request,actor:str=Query(min_length=1,max_length=100),approve:bool=True):
        from .roboflow import MAX_ROBOFLOW_ZIP_BYTES,import_zip
        store=manager().store;root=store.path('roboflow');root.mkdir(parents=True,exist_ok=True)
        temp=root/('.import_'+identity('part')+'.zip')
        try:
            length=request.headers.get('content-length')
            if length and length.isdigit() and int(length)>MAX_ROBOFLOW_ZIP_BYTES:raise ValueError('roboflow_zip_too_large')
            size=0
            with temp.open('xb') as output:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>MAX_ROBOFLOW_ZIP_BYTES:raise ValueError('roboflow_zip_too_large')
                    output.write(chunk)
            result=import_zip(store,temp,actor,approve)
            store.put('roboflow_import',result)
            return result
        except ValueError as exc:raise HTTPException(409,str(exc))
        except OSError:raise HTTPException(503,'roboflow_import_storage_unavailable')
        finally:
            temp.unlink(missing_ok=True)

    @route.post('/api/dataset/build')
    def build(body:BuildRequest):return attempt(lambda:manager().submit('build',body.model_dump()))

    @route.get('/api/datasets')
    def datasets():return manager().store.list('dataset')

    @route.get('/api/datasets/{key}/download')
    def download(key:str):
        def get():
            store=manager().store;d=store.get('dataset',key)
            return FileResponse(store.path(d['path'])/'dataset.zip',filename=key+'.zip',media_type='application/zip')
        return attempt(get)

    @route.get('/api/jobs')
    @route.get('/api/training/status')
    def jobs():return manager().status()

    @route.post('/api/jobs/{key}/cancel')
    def cancel(key:str):return attempt(lambda:manager().cancel(key))

    @route.post('/api/training/start')
    def train(body:TrainRequest):
        def run():
            from .colab_export import export_training
            path=export_training(manager().store,manager().cfg,body.model_dump())
            return FileResponse(path,filename='rack_colab_training.zip',media_type='application/zip',background=BackgroundTask(path.unlink,missing_ok=True))
        return attempt(run)

    @route.post('/api/training/evaluate')
    def evaluate(body:EvaluateRequest):return attempt(lambda:manager().submit('evaluate',body.model_dump()))

    @route.get('/api/models')
    def models():return manager().store.list('model')

    @route.get('/api/models/current')
    def current_model():
        store=manager().store
        try:name=store.get('setting','current_model_name')['name']
        except KeyError:name=manager().cfg.model.stem
        return {'id':'current','display_name':name,'filename':manager().cfg.model.name,'status':'deployed'}

    @route.post('/api/models/{key}/name')
    def name_model(key:str,body:ModelNameRequest):
        def rename():
            store=manager().store;name=body.name.strip()
            if not name:raise ValueError('model_name_required')
            if key=='current':
                value={'id':'current_model_name','name':name,'updated':__import__('time').time()}
                store.put('setting',value)
                return {'id':'current','display_name':name,'filename':manager().cfg.model.name,'status':'deployed'}
            record=store.get('model',key);record['display_name']=name;store.put('model',record);return record
        return attempt(rename)

    @route.post('/api/video-tests')
    def start_video_test(body:VideoTestRequest):
        def run():
            clip=clips().get(body.clip_id)
            if not clip.get('raw') or clip['status'] not in ('recorded','stopped'):raise ValueError('finalized_raw_clip_required')
            if body.model_id!='current':manager().store.get('model',body.model_id)
            return manager().submit('video_test',body.model_dump())
        return attempt(run)

    @route.get('/api/video-tests')
    def video_tests():return manager().store.list('video_test')

    @route.get('/api/video-tests/{key}/{kind}')
    def video_test_file(key:str,kind:Literal['video','csv']):
        def get():
            store=manager().store;record=store.get('video_test',key)
            field='video_path' if kind=='video' else 'csv_path';path=store.path(record[field])
            return FileResponse(path,media_type='video/mp4' if kind=='video' else 'text/csv',filename=None if kind=='video' else key+'_events.csv')
        return attempt(get)

    @route.get('/api/benchmarks')
    def benchmarks():return manager().store.list('benchmark')

    @route.post('/api/benchmarks')
    def benchmark(body:BenchmarkRequest):
        def add():
            clip=clips().get(body.clip_id)
            if not clip.get('raw') or clip['status'] not in ('recorded','stopped'):raise ValueError('finalized_raw_required')
            value=dict(id=identity('benchmark'),**body.model_dump(),source_hash=sha256(clips().file(body.clip_id,'raw')))
            manager().store.put('benchmark',value);return value
        return attempt(add)
    return route
