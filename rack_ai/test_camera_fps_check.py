"""ตรวจตรรกะแยกปัญหา FPS กล้อง โดยไม่ต้องมีกล้องจริง"""
from rack_ai.tools.camera_fps_check import analyse, verdict


def steady(count, fps=25, start=0.0):
    return [(start + i / fps, i * 1000 / fps) for i in range(count)]


def test_a_steady_stream_has_no_missing_or_late_frames():
    result = analyse(steady(250), 25)
    assert result['missing_frames'] == 0 and result['late_bursts'] == 0
    assert result['fps'] == 25


def test_skipped_pts_counts_as_frames_lost_at_the_source():
    frames = steady(50) + [(2.0 + i / 25, 3000 + i * 40) for i in range(50)]
    assert analyse(frames, 25)['missing_frames'] == 25


def test_continuous_pts_arriving_in_a_lump_counts_as_late_not_missing():
    frames = steady(50)
    frames += [(frames[-1][0] + 0.8, frames[-1][1] + 40)]
    result = analyse(frames, 25)
    assert result['missing_frames'] == 0 and result['late_bursts'] == 1


def test_verdict_points_at_the_camera_when_source_drops_frames():
    assert verdict({'missing_frames': 50, 'frames': 1000}, 0, 0, 60).startswith('ฝั่งกล้อง')


def test_verdict_points_at_the_system_when_only_the_service_falls_behind():
    assert verdict({'missing_frames': 0, 'frames': 1500}, 20, 0, 60).startswith('ฝั่งระบบ')


def test_verdict_points_at_the_network_when_both_readers_stall():
    assert verdict({'missing_frames': 0, 'frames': 1500}, 20, 20, 60).startswith('เครือข่าย')
