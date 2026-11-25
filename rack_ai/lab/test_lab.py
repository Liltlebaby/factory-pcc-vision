import copy
from dataclasses import asdict
import json
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from rack_ai.app import create_app
from rack_ai.config import Settings
from rack_ai.recording import ClipStore
from rack_ai.test_pipeline import FakeService
from rack_ai.runtime import CountJournal,InstanceLock
from .store import LabStore,sha256,validate_boxes
from .selector import signature
from .extractor import extract
from .builder import build,verify_dataset
from .roboflow import export_zip,import_zip
from .evaluation import counting_error,acceptance


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root=Path(self.temp.name);self.store=LabStore(self.root/'lab')
    def tearDown(self):self.temp.cleanup()
    def frame(self,i,group=None,source=None):
        rng=np.random.default_rng(i)
        image=rng.integers(0,255,(96,128,3),dtype=np.uint8)
        path=self.store.path(f'candidate/images/frame_{i}.jpg');path.parent.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(path),image)
        record=dict(id=f'frame_{i}',clip_id=f'clip_{i}',group_id=group or f'group_{i}',source_hash=source or str(i),
                    frame_index=0,second=0,image_path=str(path.relative_to(self.store.root)),image_sha256=sha256(path),
                    signature=str(signature(image)),width=128,height=96,boxes=[[.1,.2,.8,.7]],confidence=[.5],
                    review_status='pending',revision=0,negative_confirmed=False,priority='HIGH_VALUE',reasons=['uncertain_detection'])
        self.store.put('frame',record);return record
    def approve(self,record):return self.store.review(record['id'],0,'approve','tester',record['boxes'])

    def test_model_display_names(self):
        model_path=self.root/'best.pt';model_path.write_bytes(b'weights')
        cfg=Settings(model=model_path,lab_root=self.store.root,record_root=self.root/'clips')
        self.store.put('model',{'id':'model_example','status':'trained','display_name':'รุ่นเดิม'})
        with TestClient(create_app(cfg,FakeService())) as client:
            self.assertEqual(client.get('/api/models/current').json()['display_name'],'best')
            renamed=client.post('/api/models/current/name',json={'name':'โมเดลกลางคืน v2'})
            self.assertEqual(renamed.status_code,200)
            self.assertEqual(client.get('/api/models/current').json()['display_name'],'โมเดลกลางคืน v2')
            renamed=client.post('/api/models/model_example/name',json={'name':'เก๊ะแยกคู่ v3'})
            self.assertEqual(renamed.status_code,200)
            self.assertEqual(self.store.get('model','model_example')['display_name'],'เก๊ะแยกคู่ v3')
            self.assertEqual(client.post('/api/models/current/name',json={'name':'../bad'}).status_code,422)

    def test_review_revision_and_negative_gate(self):
        frame=self.frame(1)
        with self.assertRaises(ValueError):self.store.review(frame['id'],0,'approve','tester',[],False)
        approved=self.store.review(frame['id'],0,'approve','tester',[],True)
        self.assertTrue(approved['negative_confirmed'])
        with self.assertRaises(ValueError):self.store.review(frame['id'],0,'save','tester',[])
        edited=self.store.review(frame['id'],1,'save','tester',[[.1,.1,.3,.3]])
        self.assertEqual(edited['review_status'],'pending')

    def test_roboflow_yolov8_round_trip(self):
        first=self.frame(1);second=self.frame(2)
        exported,count=export_zip(self.store,'pending')
        self.assertEqual(count,2)
        with zipfile.ZipFile(exported) as archive:
            self.assertIn('images/train/frame_1.jpg',archive.namelist())
            self.assertIn('labels/train/frame_1.txt',archive.namelist())
        reviewed=self.root/'reviewed.zip'
        with zipfile.ZipFile(reviewed,'w') as archive:
            archive.writestr('labels/train/frame_1.txt','0 0.5 0.5 0.4 0.2\n')
            archive.writestr('labels/train/frame_2.txt','')
        result=import_zip(self.store,reviewed,'roboflow-reviewer',approve=True)
        self.assertEqual(result['updated'],2)
        self.assertEqual(self.store.get('frame',first['id'])['boxes'],[[.3,.4,.7,.6]])
        self.assertTrue(self.store.get('frame',second['id'])['negative_confirmed'])
        self.assertEqual(self.store.get('frame',first['id'])['review_status'],'approved')

    def test_immutable_approved_only_snapshot_and_tamper(self):
        for i in range(3):self.approve(self.frame(i))
        self.frame(99)
        dataset=build(self.store)
        self.assertEqual(dataset['report']['total_images'],3)
        _,root,manifest=verify_dataset(self.store,dataset['id'])
        self.assertEqual(set(m['split'] for m in manifest),{'train','val','test'})
        self.assertTrue((root/'dataset.zip').is_file())
        self.store.review('frame_0',1,'save','tester',[[.2,.2,.5,.5]])
        verify_dataset(self.store,dataset['id'])  # later review cannot change an existing snapshot
        (root/manifest[0]['label']).write_text('0 0 0 0 0')
        with self.assertRaises(ValueError):verify_dataset(self.store,dataset['id'])

    def test_clip_leakage_rejected(self):
        for i in range(3):self.approve(self.frame(i,source='same-video'))
        with self.assertRaisesRegex(ValueError,'same_source_clip'):build(self.store)

    def test_duplicate_and_invalid_box_rejected(self):
        for invalid in ([[-.1,.1,.4,.4]],[[.4,.1,.1,.4]],[[float('nan'),0,1,1]]):
            with self.assertRaises(ValueError):validate_boxes(invalid)
        for i in range(3):self.approve(self.frame(i))
        f=self.store.get('frame','frame_1');f['signature']=self.store.get('frame','frame_0')['signature'];self.store.put('frame',f)
        # A hash collision alone must not reject visibly different images.
        self.assertEqual(build(self.store)['report']['total_images'],3)

    def test_pixel_confirmation_preserves_duplicate_protection(self):
        from .duplicates import thumbnail,confirmed_duplicate
        image=np.full((300,300,3),100,dtype=np.uint8)
        cv2.rectangle(image,(100,100),(200,130),(220,220,220),-1)
        moved=np.full_like(image,100)
        cv2.rectangle(moved,(100,180),(200,210),(220,220,220),-1)
        self.assertTrue(confirmed_duplicate(thumbnail(image),thumbnail(image),[],[]))
        self.assertFalse(confirmed_duplicate(thumbnail(image),thumbnail(moved),[[.3,.3,.7,.5]],[[.3,.6,.7,.8]]))
        for i in range(3):self.approve(self.frame(i))
        first=self.store.get('frame','frame_0');second=self.store.get('frame','frame_1')
        # Identical decoded pixels with different file bytes: still reject.
        raw=self.store.path(first['image_path']).read_bytes()
        path=self.store.path(second['image_path']);path.write_bytes(raw+b'\n')
        second.update(image_sha256=sha256(path),signature=first['signature'])
        self.store.put('frame',second)
        with self.assertRaisesRegex(ValueError,'near_duplicate'):build(self.store)

    def test_counting_acceptance_requires_unseen_improvement(self):
        good=dict(precision=.95,recall=.95,map50=.95,map5095=.8)
        self.assertFalse(acceptance(good,good,[])['eligible'])
        result=acceptance(good,good,[dict(candidate=counting_error(50,49),baseline=counting_error(50,45))])
        self.assertTrue(result['eligible']);self.assertFalse(result['automatic_promotion'])
        self.assertIsNone(counting_error(0,1)['percentage_error'])

    def test_extraction_pending_idempotent_and_raw_only(self):
        clips=ClipStore(self.root/'clips');key='clip_'+'a'*32;path=clips.root/'raw'/f'{key}.mp4'
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),5,(128,96))
        for i in range(20):writer.write(np.random.default_rng(i).integers(0,255,(96,128,3),dtype=np.uint8))
        writer.release();clips.save(dict(clip_id=key,raw=True,status='recorded',file_path=f'raw/{key}.mp4'))
        class Labeler:
            def predict(self,frame):return [[.1,.2,.7,.8]],[.5]
        model=self.root/'fake.pt';model.write_bytes(b'fixture')
        options=dict(sample_fps=1,max_frames=3,duration_seconds=4)
        result=extract(self.store,clips,key,model,options,labeler=Labeler())
        self.assertGreater(result['saved'],0)
        frame=self.store.list('frame')[0]
        self.assertEqual(frame['review_status'],'pending')
        self.store.review(frame['id'],0,'approve','tester',frame['boxes'])
        extract(self.store,clips,key,model,options,labeler=Labeler())
        self.assertEqual(self.store.get('frame',frame['id'])['review_status'],'approved')
        clip=clips.get(key);clip['raw']=False;clips.save(clip)
        with self.assertRaises(ValueError):extract(self.store,clips,key,model,options,labeler=Labeler())

    def test_api_auth_revision_and_training_gate(self):
        cfg=Settings(lab_root=self.store.root,record_root=self.root/'clips',token='secret')
        f=self.frame(1);headers={'Authorization':'Bearer secret'}
        with TestClient(create_app(cfg,FakeService())) as client:
            self.assertEqual(client.get('/dataset').status_code,200)
            self.assertEqual(client.get('/api/dataset/stats').status_code,401)
            self.assertEqual(client.get('/api/dataset/stats',headers=headers).json()['pending'],1)
            response=client.post('/api/dataset/review/frame_1/approve',headers=headers,
                                 json=dict(revision=0,actor='tester',boxes=f['boxes']))
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.post('/api/training/start',headers=headers,json=dict(dataset_id='missing')).status_code,404)

    def test_upload_historical_raw_video(self):
        clips=ClipStore(self.root/'clips');video=self.root/'history.mp4'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),5,(128,96))
        for i in range(10):writer.write(np.full((96,128,3),i*20,dtype=np.uint8))
        writer.release();data=video.read_bytes()
        service=FakeService();service.recorder=SimpleNamespace(storage=lambda:clips)
        cfg=Settings(lab_root=self.store.root,record_root=clips.root,token='secret')
        headers={'Authorization':'Bearer secret','Content-Type':'application/octet-stream'}
        with TestClient(create_app(cfg,service)) as client:
            response=client.post('/api/recordings/upload?filename=Camera09ย้อนหลัง.mp4',headers=headers,content=data)
            self.assertEqual(response.status_code,200,response.text)
            clip=response.json();self.assertEqual(clip['source'],'upload');self.assertTrue(clip['raw'])
            self.assertEqual(clip['frames_written'],10);self.assertTrue(clips.file(clip['clip_id']).is_file())
            duplicate=client.post('/api/recordings/upload?filename=again.mp4',headers=headers,content=data)
            self.assertEqual(duplicate.status_code,409);self.assertIn('video_already_imported',duplicate.text)
            invalid=client.post('/api/recordings/upload?filename=video.exe',headers=headers,content=data)
            self.assertEqual(invalid.status_code,409)
        self.assertFalse(list((clips.root/'raw').glob('.upload_*')))

    def test_count_journal_restart(self):
        journal=CountJournal(self.root/'runtime');self.assertEqual(journal.start(),0)
        event={'rackNumber':11,'trackId':7,'timestamp':1700000000.25,'confidence':.93,'model_version':'best.pt'}
        next_event={'rackNumber':12,'trackId':8,'timestamp':1700000001.25,'confidence':.91,'model_version':'best.pt'}
        journal.submit(11,event);journal.submit(11,event);journal.submit(12,next_event);journal.close()
        second=CountJournal(self.root/'runtime');self.assertEqual(second.start(),12);second.close()
        first=second.events(limit=1)
        self.assertEqual(len(first['items']),1);self.assertTrue(first['has_more'])
        self.assertEqual(first['items'][0]['payload']['rubber_count'],11)
        page=second.events(after=first['next_cursor'],limit=10)
        self.assertEqual(len(page['items']),1);self.assertFalse(page['has_more'])
        self.assertEqual(page['items'][0]['payload']['rubber_count'],12)

    def test_single_instance_and_origin(self):
        with InstanceLock(self.root/'runtime'):
            with self.assertRaises((RuntimeError,OSError)):
                with InstanceLock(self.root/'runtime'):pass
        with InstanceLock(self.root/'runtime'):pass
        cfg=Settings(lab_root=self.store.root,record_root=self.root/'clips')
        with TestClient(create_app(cfg,FakeService())) as client:
            response=client.post('/api/dataset/build',headers={'Origin':'https://untrusted.example'},json={})
            self.assertEqual(response.status_code,403)

    def test_training_version_and_evaluation_without_promotion(self):
        from .training import train,evaluate
        for i in range(3):self.approve(self.frame(i))
        dataset=build(self.store);baseline=self.root/'best.pt';baseline.write_bytes(b'original-model')
        cfg=Settings(model=baseline,lab_root=self.store.root,record_root=self.root/'clips')
        class FakeYOLO:
            def __init__(self,path):self.path=path
            def add_callback(self,name,callback):self.callback=callback
            def train(self,**kwargs):
                destination=Path(kwargs['project'])/kwargs['name']
                (destination/'weights').mkdir(parents=True)
                (destination/'weights/best.pt').write_bytes(b'new-model')
                self.trainer=SimpleNamespace(save_dir=destination,epoch=0)
                self.callback(self.trainer)
            def val(self,**kwargs):
                return SimpleNamespace(box=SimpleNamespace(mp=.95,mr=.95,map50=.95,map=.85),
                                       confusion_matrix=SimpleNamespace(matrix=np.array([[19,1],[1,0]])))
        with patch('ultralytics.YOLO',FakeYOLO):
            record=train(self.store,cfg,dict(dataset_id=dataset['id'],epochs=1,imgsz=64,batch=1))
            self.assertEqual(baseline.read_bytes(),b'original-model')
            self.assertEqual((self.store.path(record['path'])/'baseline.pt').read_bytes(),b'original-model')
            result=evaluate(self.store,ClipStore(cfg.record_root),cfg,dict(model_id=record['id']))
            self.assertFalse(result['decision']['eligible'])
            self.assertEqual(result['candidate']['false_positives'],1)
            self.assertEqual(baseline.read_bytes(),b'original-model')

    def test_worker_preserves_serializable_job_config(self):
        from .worker import main
        cfg=asdict(Settings(lab_root=self.store.root,record_root=self.root/'clips'))
        cfg={key:str(value) if isinstance(value,Path) else value for key,value in cfg.items()}
        self.store.put('job',dict(id='job_test',type='build',config=cfg,options={},status='queued'))
        with patch('sys.argv',['worker','--root',str(self.store.root),'--job','job_test']):main()
        job=self.store.get('job','job_test')
        self.assertEqual(job['status'],'failed')
        self.assertEqual(job['error'],'no_approved_images')
        self.assertIsInstance(job['config']['lab_root'],str)

    def test_annotated_video_test_and_download(self):
        from .video_test import analyze
        clips=ClipStore(self.root/'clips');key='clip_'+'b'*32;path=clips.root/'raw'/f'{key}.mp4'
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),5,(128,96))
        for i in range(10):writer.write(np.full((96,128,3),40+i,dtype=np.uint8))
        writer.release();clips.save(dict(clip_id=key,raw=True,status='recorded',file_path=f'raw/{key}.mp4'))
        model=self.root/'best.pt';model.write_bytes(b'current-model')
        cfg=Settings(model=model,lab_root=self.store.root,record_root=clips.root,line=.5,movement=5,cooldown=0)
        class Detector:
            index=0
            def infer(self,frame):
                centers=[20,30,40,52,65,70,72,74,76,78];center=centers[self.index];self.index+=1
                return [dict(track_id=1,class_id=0,class_name='rack',confidence=.9,bbox=[20,center-8,105,center+8])]
        result=analyze(self.store,clips,cfg,dict(clip_id=key,model_id='current',start_seconds=0,duration_seconds=2,sample_fps=5),detector=Detector(),web_encode=False)
        self.assertEqual(result['count'],1);self.assertEqual(result['events'],1)
        self.assertTrue(self.store.path(result['video_path']).is_file())
        self.assertIn('rack_number',self.store.path(result['csv_path']).read_text(encoding='utf-8-sig'))
        service=FakeService();service.recorder=SimpleNamespace(storage=lambda:clips)
        with TestClient(create_app(cfg,service)) as client:
            self.assertEqual(client.get(f"/api/video-tests/{result['id']}/video").status_code,200)
            self.assertEqual(client.get(f"/api/video-tests/{result['id']}/csv").status_code,200)


if __name__=='__main__':unittest.main()
