"""Opt-in real YOLO API smoke test on disposable synthetic data, not an accuracy test."""
from pathlib import Path

from rack_ai.config import Settings
from rack_ai.recording import ClipStore
from .builder import build
from .training import train,evaluate
from .test_lab import LabTests


def main() -> None:
    fixture=LabTests()
    fixture.setUp()
    try:
        for index in range(3):
            fixture.approve(fixture.frame(index))
        dataset=build(fixture.store)
        cfg=Settings(model=Path('ai/rack_detector/runs/rack_yolo11n/weights/best.pt').resolve(),
                     lab_root=fixture.store.root,record_root=fixture.root/'clips')
        model=train(fixture.store,cfg,dict(dataset_id=dataset['id'],epochs=1,imgsz=64,batch=1))
        result=evaluate(fixture.store,ClipStore(cfg.record_root),cfg,dict(model_id=model['id']))
        assert result['decision']['automatic_promotion'] is False
        print('SMOKE_OK: synthetic only; trained and evaluated; no model deployment')
    finally:
        fixture.tearDown()


if __name__=='__main__':
    main()
