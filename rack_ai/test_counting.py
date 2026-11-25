"""Counting regression tests focused on racks that travel touching.

Run from the project root:  python -m unittest rack_ai.test_counting -v
"""
import unittest

from rack_ai.config import Settings
from rack_ai.counter import RackCounter, box_iou, containment


HEIGHT = 100


def box(y, x1=0.0, x2=40.0, half=6.0):
    """A rack box centred on y."""
    return [x1, y-half, x2, y+half]


def drive(counter, track_id, ys, start=0.0, step=0.2, x1=0.0, x2=40.0):
    """Feed one track down the frame, one detection per frame."""
    for index, y in enumerate(ys):
        counter.update([dict(track_id=track_id, confidence=.9, bbox=box(y, x1, x2))],
                       HEIGHT, start+index*step)


def interleave(counter, first, second, start=0.0, step=0.2):
    """Feed two tracks that are visible in the same frames."""
    for index, (a, b) in enumerate(zip(first[1], second[1])):
        detections = []
        if a is not None:
            detections.append(dict(track_id=first[0], confidence=.9, bbox=box(a, *first[2])))
        if b is not None:
            detections.append(dict(track_id=second[0], confidence=.9, bbox=box(b, *second[2])))
        counter.update(detections, HEIGHT, start+index*step)


class SpatialDedupeTests(unittest.TestCase):
    def settings(self, **kw):
        base = dict(line=.5, movement=5, cooldown=1.5, dedupe='spatial')
        base.update(kw)
        return Settings(**base)

    def test_two_touching_racks_are_both_counted(self):
        """The regression this change exists for.

        Two distinct racks cross 0.6 s apart -- inside the 1.5 s cooldown. The
        old global cooldown counted one; both must now be counted because their
        boxes do not overlap.
        """
        counter = RackCounter(self.settings())
        lead = (1, [20, 30, 40, 52, 60, 70, 80, 90], (0.0, 40.0))
        follow = (2, [None, None, 18, 26, 34, 44, 56, 66], (0.0, 40.0))
        interleave(counter, lead, follow)
        self.assertEqual(counter.count, 2)
        self.assertEqual(counter.suppressed, 0)

    def test_split_box_of_one_rack_counts_once(self):
        """Two heavily overlapping tracks are one physical rack, not two."""
        counter = RackCounter(self.settings())
        path = [20, 30, 40, 52, 60, 70]
        first = (1, path, (0.0, 40.0))
        second = (2, path, (2.0, 41.0))   # near-identical box, IoU well above .55
        interleave(counter, first, second)
        self.assertEqual(counter.count, 1)
        self.assertGreaterEqual(counter.suppressed, 1)

    def test_contained_fragment_counts_once(self):
        """A small fragment inside a counted box is the same rack."""
        counter = RackCounter(self.settings())
        path = [20, 30, 40, 52, 60, 70]
        big = (1, path, (0.0, 40.0))
        fragment = (2, path, (8.0, 30.0))   # sits inside the big box
        interleave(counter, big, fragment)
        self.assertEqual(counter.count, 1)

    def test_suppressed_rack_is_still_counted_after_the_window(self):
        """Suppression delays a genuine rack, it must never drop it."""
        counter = RackCounter(self.settings())
        drive(counter, 1, [20, 30, 40, 52, 60], start=0.0)
        # Same box shape, so the guard fires, but the track keeps travelling.
        drive(counter, 2, [20, 30, 40, 52, 58, 64, 70, 76, 82], start=0.4, step=0.3)
        self.assertEqual(counter.count, 2)

    def test_global_mode_reproduces_previous_behaviour(self):
        counter = RackCounter(self.settings(dedupe='global'))
        lead = (1, [20, 30, 40, 52, 60, 70, 80, 90], (0.0, 40.0))
        follow = (2, [None, None, 18, 26, 34, 44, 56, 66], (0.0, 40.0))
        interleave(counter, lead, follow)
        self.assertEqual(counter.count, 1)      # the rack behind is swallowed
        self.assertGreaterEqual(counter.suppressed, 1)

    def test_reset_tracks_clears_duplicate_memory(self):
        counter = RackCounter(self.settings())
        drive(counter, 1, [20, 30, 40, 52, 60])
        self.assertEqual(counter.count, 1)
        counter.reset_tracks()
        self.assertEqual(len(counter.tracks), 0)
        self.assertEqual(counter.count, 1)   # total survives a reconnect

    def test_upward_movement_still_not_counted(self):
        counter = RackCounter(self.settings())
        drive(counter, 1, [80, 70, 60, 40, 20])
        self.assertEqual(counter.count, 0)

    def test_rack_born_below_the_line_is_not_counted(self):
        counter = RackCounter(self.settings())
        drive(counter, 1, [60, 70, 80, 90])
        self.assertEqual(counter.count, 0)


class GeometryTests(unittest.TestCase):
    def test_iou_and_containment(self):
        a = [0, 0, 10, 10]
        self.assertAlmostEqual(box_iou(a, a), 1.0)
        self.assertAlmostEqual(box_iou(a, [20, 20, 30, 30]), 0.0)
        self.assertAlmostEqual(containment(a, [2, 2, 8, 8]), 1.0)   # fully inside
        self.assertLess(box_iou(a, [2, 2, 8, 8]), 0.4)

    def test_settings_validation(self):
        for args in (dict(dedupe='sometimes'), dict(duplicate_iou=1.5), dict(duplicate_containment=-.1)):
            with self.assertRaises(ValueError):
                Settings(**args)


if __name__ == '__main__':
    unittest.main()
