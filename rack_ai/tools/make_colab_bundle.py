"""Pack the live counting code into one zip that runs on Colab.

Why this exists
---------------
The existing Colab notebooks ship ``offline_track_count.py``, which counts with
different rules from the service. Testing there answers a question nobody asked.
This bundle contains the modules the service itself uses -- detector, counter,
config, preview filter, the geometry filter and the offline tools -- so a count
measured on Colab is the count the service produces.

The bundle is built from the working tree, so it is never stale: rebuild it
after changing any counting code and upload it again.

Usage (from the project root)::

    python -m rack_ai.tools.make_colab_bundle
    python -m rack_ai.tools.make_colab_bundle --model ai/rack_detector/runs/rack_yolo11n/weights/best.pt
    python -m rack_ai.tools.make_colab_bundle --output D:\\upload\\rack_ai_colab.zip
"""
import argparse
import sys
import zipfile
from pathlib import Path

from ..config import Settings


MODULES = [
    'rack_ai/__init__.py',
    'rack_ai/config.py',
    'rack_ai/counter.py',
    'rack_ai/detector.py',
    'rack_ai/preview_filter.py',
    'rack_ai/lab/__init__.py',
    'rack_ai/lab/store.py',
    'rack_ai/tools/__init__.py',
    'rack_ai/tools/count_video.py',
    'rack_ai/tools/tune_counting.py',
    'ai/rack_detector/offline_track_count.py',
]
README = """# rack_ai Colab bundle

Unpacked at /content/rack_ai_bundle. Run from that directory so `rack_ai` and
`ai` are importable:

    cd /content/rack_ai_bundle
    python -m rack_ai.tools.count_video --video clip.mp4 --model best.pt --expected 24

This is the same detector and counter the service runs, so the count here is
the count the service produces. `offline_track_count.py` is included only
because `detector.py` imports `filter_racks` from it -- do not count with it.

Set RACK_HALF=off when tuning on a GPU for a CPU deployment.
"""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path('.'), help='project root')
    parser.add_argument('--output', type=Path, default=Path('rack_ai_colab_bundle.zip'))
    parser.add_argument('--model', type=Path, default=None,
                        help='include these weights in the bundle (defaults to RACK_MODEL_PATH; '
                             'pass --no-model to leave them out)')
    parser.add_argument('--no-model', action='store_true',
                        help='ship code only, upload the weights separately')
    return parser.parse_args(argv)


def collect(root):
    missing = [name for name in MODULES if not (root/name).is_file()]
    if missing:
        raise SystemExit('missing from the working tree:\n  '+'\n  '.join(missing)
                         + '\nRun this from the project root, or pass --root.')
    return [(root/name, name) for name in MODULES]


def main(argv=None):
    args = parse_args(argv)
    root = args.root.resolve()
    files = collect(root)

    model = None
    if not args.no_model:
        model = args.model or Settings().model
        model = (root/model) if not Path(model).is_absolute() else Path(model)
        if not model.is_file():
            print(f'weights not found, packing code only: {model}', file=sys.stderr)
            model = None

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
        archive.writestr('README.md', README)
        if model is not None:
            archive.write(model, 'weights/best.pt')

    size = args.output.stat().st_size/1e6
    print(f'wrote {args.output}  ({size:.1f} MB, {len(files)+1+(model is not None)} entries)')
    if model is not None:
        print(f'  weights: {model.name} -> weights/best.pt')
    else:
        print('  no weights included; upload best.pt to Colab separately')
    print('\nUpload it to MyDrive/rack_counter/ together with a clip, then open')
    print('notebooks/colab/rack_ai_colab.ipynb in Colab.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
