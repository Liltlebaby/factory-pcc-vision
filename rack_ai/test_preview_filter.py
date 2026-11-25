import copy
import unittest

from rack_ai.preview_filter import select_preview_tracks


def rack(identity, box, counted=False):
    return dict(track_id=identity, bbox=box, counted=counted, confidence=.5)


class PreviewTests(unittest.TestCase):
    def test_fragments_hidden_without_mutating_tracks(self):
        tracks = [rack(1,[100,700,700,1000],True),
                  rack(2,[110,700,480,990]), rack(3,[160,705,570,970])]
        original = copy.deepcopy(tracks)
        self.assertEqual(select_preview_tracks(tracks,600),[tracks[0]])
        self.assertEqual(tracks,original)

    def test_adjacent_rack_remains(self):
        tracks = [rack(1,[100,700,700,1000],True),rack(2,[120,610,680,820])]
        self.assertEqual(select_preview_tracks(tracks,600),tracks)

    def test_duplicate_crossing_line_hidden(self):
        tracks = [rack(1,[100,500,700,800],True),rack(2,[110,510,500,790])]
        self.assertEqual(select_preview_tracks(tracks,600),[tracks[0]])

    def test_duplicate_boxes_before_line_are_hidden(self):
        tracks = [rack(1,[100,200,700,500],True),rack(2,[110,210,500,490])]
        self.assertEqual(select_preview_tracks(tracks,600),[tracks[0]])

    def test_large_wrapping_ghost_hidden(self):
        tracks = [rack(24,[130,370,404,484],True),rack(19,[114,282,427,490])]
        self.assertEqual(select_preview_tracks(tracks,417),[tracks[0]])

    def test_counted_tracks_both_remain(self):
        tracks = [rack(1,[100,700,700,1000],True),rack(2,[110,700,480,990],True)]
        self.assertEqual(select_preview_tracks(tracks,600),tracks)

    def test_no_counted_anchor_no_suppression(self):
        tracks = [rack(1,[100,700,700,1000]),rack(2,[110,700,480,990])]
        self.assertEqual(select_preview_tracks(tracks,600),[tracks[0]])

    def test_side_by_side_remain(self):
        tracks = [rack(1,[100,700,400,1000],True),rack(2,[380,700,700,1000])]
        self.assertEqual(select_preview_tracks(tracks,600),tracks)

    def test_stacked_racks_in_depth_remain(self):
        tracks = [rack(137,[344,281,582,381]),rack(130,[268,369,589,505])]
        self.assertEqual(select_preview_tracks(tracks,592),tracks)

    def test_three_fragments_of_one_uncounted_rack_collapse(self):
        tracks = [rack(130,[268,369,589,505]),rack(131,[274,382,581,493]),
                  rack(132,[283,414,584,464])]
        original = copy.deepcopy(tracks)
        self.assertEqual(select_preview_tracks(tracks,592),[tracks[0]])
        self.assertEqual(tracks,original)
