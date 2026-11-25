"""Tests for the offline operator tools.

Run from the project root:  python -m unittest rack_ai.test_tools -v
"""
import json
import tempfile
import unittest
from pathlib import Path

from rack_ai.config import Settings
from rack_ai.lab.store import LabStore
from rack_ai.tools import (reopen_rejected, register_benchmark, tune_counting,
                           count_video, make_colab_bundle)


def frame(key, group, boxes, auto, status='rejected', brightness=120.0, blur=200.0):
    return dict(id=key, clip_id=group, group_id=group, source_hash='hash_'+group,
                frame_index=0, second=1.0, image_path='candidate/images/'+key+'.jpg',
                image_sha256='x'*64, model_sha256='y'*64, width=960, height=1080,
                boxes=boxes, auto_boxes=auto, confidence=[.5]*len(auto),
                review_status=status, revision=1, reviewed_by='tester',
                negative_confirmed=False, signature=0, priority='HIGH_VALUE',
                reasons=['overlap', 'multiple_racks'], brightness=brightness, blur=blur,
                created=0.0)


def unit_boxes(count):
    """`count` valid normalised boxes that do not overlap."""
    return [[.01+i*.05, .10, .05+i*.05, .20] for i in range(count)]


class ReopenRejectedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = LabStore(self.root)
        self.store.put('frame', frame('frame_a', 'clip_one', unit_boxes(6), unit_boxes(6)))
        self.store.put('frame', frame('frame_b', 'clip_one', unit_boxes(2), unit_boxes(2)))
        self.store.put('frame', frame('frame_c', 'clip_two', unit_boxes(9), unit_boxes(9)))
        self.store.put('frame', frame('frame_ok', 'clip_two', unit_boxes(3), unit_boxes(3),
                                      status='approved'))
        self.addCleanup(self.temporary.cleanup)

    def args(self, **kw):
        base = ['--lab-root', str(self.root)]
        for key, value in kw.items():
            base += ['--'+key.replace('_', '-'), str(value)]
        return reopen_rejected.parse_args(base)

    def test_only_rejected_frames_are_candidates(self):
        rows = reopen_rejected.candidates(self.store, self.args())
        self.assertEqual({r['frame_id'] for r in rows}, {'frame_a', 'frame_b', 'frame_c'})

    def test_sorted_by_box_count_so_hard_frames_come_first(self):
        rows = reopen_rejected.candidates(self.store, self.args())
        self.assertEqual([r['frame_id'] for r in rows], ['frame_c', 'frame_a', 'frame_b'])

    def test_min_boxes_filters_out_easy_frames(self):
        rows = reopen_rejected.candidates(self.store, self.args(min_boxes=5))
        self.assertEqual({r['frame_id'] for r in rows}, {'frame_a', 'frame_c'})

    def test_group_filter(self):
        rows = reopen_rejected.candidates(self.store, self.args(group='clip_two'))
        self.assertEqual([r['frame_id'] for r in rows], ['frame_c'])

    def test_list_mode_changes_nothing(self):
        reopen_rejected.main(['--lab-root', str(self.root), '--list'])
        self.assertEqual(self.store.get('frame', 'frame_a')['review_status'], 'rejected')

    def test_reopen_sets_pending_and_keeps_boxes(self):
        reopen_rejected.main(['--lab-root', str(self.root), '--actor', 'tle', '--min-boxes', '5'])
        reopened = self.store.get('frame', 'frame_a')
        self.assertEqual(reopened['review_status'], 'pending')
        self.assertEqual(len(reopened['boxes']), 6)
        self.assertEqual(self.store.get('frame', 'frame_b')['review_status'], 'rejected')
        self.assertEqual(self.store.get('frame', 'frame_ok')['review_status'], 'approved')

    def test_reopen_requires_an_actor(self):
        with self.assertRaises(SystemExit):
            reopen_rejected.main(['--lab-root', str(self.root)])


class RegisterBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.lab = self.root/'lab'
        self.records = self.root/'recordings'
        (self.records/'raw').mkdir(parents=True)
        self.store = LabStore(self.lab)
        for name, payload in (('clip_'+'a'*32, b'unseen clip bytes'), ('clip_'+'b'*32, b'used clip bytes')):
            (self.records/'raw'/(name+'.mp4')).write_bytes(payload)
            (self.records/(name+'.json')).write_text(
                json.dumps(dict(clip_id=name, name=name, status='recorded')), encoding='utf-8')
        self.addCleanup(self.temporary.cleanup)

    def mark_used(self, clip_id):
        digest = register_benchmark.sha256(self.records/'raw'/(clip_id+'.mp4'))
        self.store.put('frame', dict(frame('frame_used', clip_id, unit_boxes(1), unit_boxes(1),
                                           status='approved'), source_hash=digest))

    def run_tool(self, *argv):
        return register_benchmark.main(['--lab-root', str(self.lab),
                                        '--record-root', str(self.records), *argv])

    def test_clip_rows_flag_clips_already_in_a_dataset(self):
        self.mark_used('clip_'+'b'*32)
        rows = {r['clip_id']: r for r in register_benchmark.clip_rows(self.store, self.records)}
        self.assertTrue(rows['clip_'+'a'*32]['unseen'])
        self.assertFalse(rows['clip_'+'b'*32]['unseen'])

    def test_registering_an_unseen_clip(self):
        self.run_tool('--clip-id', 'clip_'+'a'*32, '--expected', '24', '--actor', 'tle')
        rows = self.store.list('benchmark')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['expected_count'], 24)
        self.assertEqual(rows[0]['clip_id'], 'clip_'+'a'*32)

    def test_refuses_a_clip_that_fed_the_dataset(self):
        self.mark_used('clip_'+'b'*32)
        with self.assertRaises(SystemExit):
            self.run_tool('--clip-id', 'clip_'+'b'*32, '--expected', '5', '--actor', 'tle')
        self.assertEqual(self.store.list('benchmark'), [])

    def test_refuses_an_unknown_clip(self):
        with self.assertRaises(SystemExit):
            self.run_tool('--clip-id', 'clip_'+'c'*32, '--expected', '5', '--actor', 'tle')


class CountVideoTests(unittest.TestCase):
    def test_overrides_only_replace_what_was_given(self):
        args = count_video.parse_args(['--video', 'c.mp4', '--iou', '.45', '--dedupe', 'global'])
        settings = count_video.apply_overrides(Settings(line=.6, confidence=.55), args)
        self.assertEqual(settings.iou, .45)
        self.assertEqual(settings.dedupe, 'global')
        self.assertEqual(settings.confidence, .55)     # untouched
        self.assertEqual(settings.line, .6)            # untouched

    def test_no_overrides_returns_the_same_settings(self):
        args = count_video.parse_args(['--video', 'c.mp4'])
        base = Settings()
        self.assertIs(count_video.apply_overrides(base, args), base)

    def test_half_override_reaches_settings(self):
        args = count_video.parse_args(['--video', 'c.mp4', '--half', 'off'])
        self.assertEqual(count_video.apply_overrides(Settings(), args).half, 'off')

    def test_video_is_required(self):
        with self.assertRaises(SystemExit):
            count_video.parse_args([])


class MakeColabBundleTests(unittest.TestCase):
    def test_bundle_carries_every_module_the_counter_imports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in make_colab_bundle.MODULES:
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# stub\n', encoding='utf-8')
            weights = root/'best.pt'
            weights.write_bytes(b'weights')
            output = root/'bundle.zip'
            make_colab_bundle.main(['--root', str(root), '--output', str(output),
                                    '--model', 'best.pt'])
            import zipfile
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertTrue(set(make_colab_bundle.MODULES) <= names)
            self.assertIn('weights/best.pt', names)
            self.assertIn('README.md', names)

    def test_missing_module_is_reported_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'rack_ai').mkdir()
            (root/'rack_ai/config.py').write_text('# stub\n', encoding='utf-8')
            with self.assertRaises(SystemExit):
                make_colab_bundle.collect(root)

    def test_real_working_tree_has_every_bundled_module(self):
        root = Path(__file__).resolve().parents[1]
        missing = [name for name in make_colab_bundle.MODULES if not (root/name).is_file()]
        self.assertEqual(missing, [], f'bundle list is out of date: {missing}')


class TuneCountingTests(unittest.TestCase):
    def test_video_and_expected_are_paired_in_order(self):
        args = tune_counting.parse_args(['--video', 'a.mp4', '--expected', '12',
                                         '--video', 'b.mp4', '--expected', '9'])
        self.assertEqual([(str(p), e) for p, e in args.pairs], [('a.mp4', 12), ('b.mp4', 9)])

    def test_expected_without_video_is_rejected(self):
        with self.assertRaises(SystemExit):
            tune_counting.parse_args(['--expected', '3'])

    def test_video_without_expected_is_rejected(self):
        with self.assertRaises(SystemExit):
            tune_counting.parse_args(['--video', 'a.mp4'])

    def test_cache_key_separates_every_input(self):
        base = ('m'*64, 'c'*64, .55, .70, 640, 5.0, 0.0, 0.0)
        keys = {tune_counting.cache_key(*base)}
        for index, value in ((2, .45), (3, .35), (4, 960), (5, 2.0), (6, 30.0), (7, 600.0)):
            changed = list(base)
            changed[index] = value
            keys.add(tune_counting.cache_key(*changed))
        self.assertEqual(len(keys), 7)

    def test_grid_has_no_redundant_rows(self):
        options = list(tune_counting.counter_options())
        markers = {tuple(sorted(o.items())) for o in options}
        self.assertEqual(len(options), len(markers))
        # A zero cooldown makes the dedupe mode meaningless, so it must collapse.
        self.assertEqual({o['dedupe'] for o in options if o['cooldown'] == 0}, {'spatial'})

    def test_replay_counts_from_cached_detections(self):
        frames = []
        for index, y in enumerate([20, 30, 40, 52, 60, 70]):
            frames.append(dict(second=index*.2, detections=[
                dict(track_id=1, confidence=.9, bbox=[0., y-6., 40., y+6.])]))
        option = dict(line=.5, anchor='center', movement=5, cooldown=1.5,
                      dedupe='spatial', duplicate_iou=.55)
        count, suppressed = tune_counting.replay(frames, 100, option, Settings())
        self.assertEqual((count, suppressed), (1, 0))

    def test_replay_does_not_mutate_the_cache(self):
        frames = [dict(second=0., detections=[dict(track_id=1, confidence=.9, bbox=[0., 1., 2., 3.])])]
        before = json.dumps(frames)
        option = dict(line=.5, anchor='center', movement=5, cooldown=0.,
                      dedupe='spatial', duplicate_iou=.55)
        tune_counting.replay(frames, 100, option, Settings())
        tune_counting.replay(frames, 100, option, Settings())
        self.assertEqual(json.dumps(frames), before)

    def test_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'det.jsonl'
            path.write_text(json.dumps(dict(kind='header', height=1080, fps=25., stride=5,
                                            conf=.55, iou=.7))+'\n'
                            + json.dumps(dict(second=.2, detections=[]))+'\n', encoding='utf-8')
            header, frames = tune_counting.load_cache(path)
            self.assertEqual(header['height'], 1080)
            self.assertEqual(len(frames), 1)

    def test_tie_break_prefers_settings_close_to_what_is_deployed(self):
        settings = Settings()
        near = tune_counting.distance_from_deployed(dict(tune_counting.DEPLOYED), .55, .70, settings)
        far = tune_counting.distance_from_deployed(
            dict(line=.75, anchor='top', movement=30, cooldown=5.), .25, .10, settings)
        self.assertLess(near, far)


if __name__ == '__main__':
    unittest.main()
