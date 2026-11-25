"""Portable Colab training bundle using a verified dataset snapshot."""
import json
import zipfile
from pathlib import Path
from .builder import verify_dataset
from .store import identity


def notebook(options):
    cells=[]
    def add(text, markdown=False):
        cell=dict(cell_type='markdown' if markdown else 'code',metadata={},source=text.splitlines(True))
        if not markdown:cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    add('# เทรน Rack Monitor บน Google Colab\nเลือก Runtime > Change runtime type > GPU แล้วรันจากบนลงล่าง อัปโหลด rack_colab_training.zip ในช่องที่ถาม ผลและ checkpoint จะอยู่ใน Google Drive\n',True)
    add('%pip install -q "ultralytics>=8.4,<9" lap\nimport torch\nassert torch.cuda.is_available(), "เลือก GPU runtime ก่อนเทรน"\nprint(torch.cuda.get_device_name(0))\n')
    add('from google.colab import drive, files\nfrom pathlib import Path\nimport zipfile, json, yaml, shutil\ndrive.mount("/content/drive")\nprint("เลือก rack_colab_training.zip")\nuploaded=files.upload()\npackages=[Path(n) for n in uploaded if n.endswith(".zip")]\nassert len(packages)==1, "เลือก ZIP หนึ่งไฟล์"\nwork=Path("/content/rack_training")\nwork.mkdir(exist_ok=True)\nwith zipfile.ZipFile(packages[0]) as z:\n    assert all((work / n).resolve().is_relative_to(work.resolve()) for n in z.namelist())\n    z.extractall(work)\nconfig=yaml.safe_load((work/"data.yaml").read_text())\nconfig["path"]=str(work)\n(work/"data.yaml").write_text(yaml.safe_dump(config))\noptions=json.loads((work/"training_options.json").read_text())\n')
    add('from ultralytics import YOLO\nfrom datetime import datetime\nEPOCHS=options["epochs"]\nBATCH=options["batch"]\nIMGSZ=options["imgsz"]\nrun_name="rack_"+datetime.now().strftime("%Y%m%d_%H%M%S")\noutput=Path("/content/drive/MyDrive/rack_counter/colab_training")\noutput.mkdir(parents=True,exist_ok=True)\nmodel=YOLO(str(work/"baseline.pt"))\nmodel.train(data=str(work/"data.yaml"),epochs=EPOCHS,batch=BATCH,imgsz=IMGSZ,device=0,workers=2,cache=False,project=str(output),name=run_name,patience=20,save=True,save_period=5,degrees=2,translate=.08,scale=.3,perspective=.0005,hsv_v=.35,fliplr=0.0)\nrun=Path(model.trainer.save_dir)\nprint("โมเดลที่เทรนแล้ว:",run/"weights/best.pt")\n')
    add('trained=YOLO(str(run/"weights/best.pt"))\nmetrics=trained.val(data=str(work/"data.yaml"),split="test",device=0)\nreport={"precision":float(metrics.box.mp),"recall":float(metrics.box.mr),"map50":float(metrics.box.map50),"map5095":float(metrics.box.map),"dataset_id":options["dataset_id"],"name":options["name"]}\n(run/"colab_metrics.json").write_text(json.dumps(report,indent=2))\nprint(report)\nfiles.download(str(run/"weights/best.pt"))\n')
    add('## ทดสอบกรอบบนวิดีโอ\nส่วนนี้ทดสอบการตรวจจับ ยังไม่ใช่ benchmark การนับข้ามเส้นของ Rack Monitor\n',True)
    add('print("เลือกวิดีโอ RAW หนึ่งไฟล์")\nvideo_files=files.upload()\nvideos=[Path(n) for n in video_files if Path(n).suffix.lower() in (".mp4",".avi",".mov",".mkv")]\nassert len(videos)==1\nfor result in trained.predict(source=str(videos[0]),stream=True,save=True,device=0,project="/content/rack_test",name="video",exist_ok=True,verbose=False):\n    pass\nprint("ผลทดสอบอยู่ใน /content/rack_test/video")\n')
    add('import subprocess\nfrom IPython.display import Video, display\noutputs=[p for p in Path("/content/rack_test/video").iterdir() if p.suffix.lower() in (".mp4",".avi",".mov",".mkv")]\nassert len(outputs)==1\nweb=output/(run_name+"_test.mp4")\nsubprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(outputs[0]),"-an","-c:v","libx264","-preset","fast","-pix_fmt","yuv420p",str(web)],check=True)\npreview=Path("/content/preview.mp4")\nsubprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(web),"-t","30","-vf","scale=640:-2",str(preview)],check=True)\ndisplay(Video(str(preview),embed=True))\nprint("วิดีโอเต็มบันทึกใน Drive:",web)\n')
    return dict(nbformat=4,nbformat_minor=5,metadata=dict(kernelspec=dict(name='python3',display_name='Python 3'),language_info=dict(name='python'),accelerator='GPU'),cells=cells)


def export_training(store,cfg,options):
    _,root,_=verify_dataset(store,options['dataset_id'])
    destination=store.path('colab');destination.mkdir(exist_ok=True)
    path=destination/(identity('colab')+'.zip')
    with zipfile.ZipFile(root/'dataset.zip') as source, zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():target.writestr(item.filename,source.read(item))
        target.write(cfg.model,'baseline.pt')
        target.writestr('training_options.json',json.dumps(options,ensure_ascii=False))
        target.writestr('rack_colab_train.ipynb',json.dumps(notebook(options),ensure_ascii=False,indent=2))
    return path
