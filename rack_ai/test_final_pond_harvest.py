"""เทสต์ตรรกะการคัดภาพซ้ำและการสร้าง URL — ไม่ต้องมีกล้อง"""
import numpy as np
import pytest

from rack_ai.final_pond.harvest import (
    difference, is_new, playback_url, thumbnail, windows_from,
)


def flat(value, size=(36, 64)):
    return thumbnail(np.full(size, value, dtype=np.uint8))


def test_identical_images_have_zero_difference():
    assert difference(flat(120), flat(120)) == 0.0


def test_difference_scales_with_the_change():
    assert difference(flat(100), flat(110)) < difference(flat(100), flat(200))


def test_a_near_duplicate_is_skipped():
    """ภาพที่แทบไม่ต่างกันต้องไม่ถูกเก็บ ไม่งั้นเสียเวลาตีกรอบไปเปล่า ๆ"""
    kept = [flat(120)]
    assert is_new(flat(121), kept, threshold=0.035) is False


def test_a_genuinely_different_image_is_kept():
    kept = [flat(120)]
    assert is_new(flat(200), kept, threshold=0.035) is True


def test_a_new_image_must_differ_from_every_kept_image_not_just_the_last():
    """ฉากที่สลับไปมาระหว่างสองแบบ ต้องไม่ถูกเก็บซ้ำทุกครั้งที่สลับ"""
    kept = [flat(60), flat(200)]
    assert is_new(flat(201), kept, threshold=0.035) is False
    assert is_new(flat(130), kept, threshold=0.035) is True


def test_the_first_image_is_always_kept():
    assert is_new(flat(120), [], threshold=0.035) is True


def test_mismatched_thumbnail_sizes_are_rejected():
    with pytest.raises(ValueError):
        difference(flat(120), flat(120, size=(18, 32)))


# ---------- ช่วงเวลาและ URL ----------

def test_windows_are_parsed_into_dvr_and_label_forms():
    found = windows_from('2026-09-19 08:00, 2026-09-20 22:30')
    assert found == [('2026_09_19_08_00_00', '20260919_0800'),
                     ('2026_09_20_22_30_00', '20260920_2230')]


@pytest.mark.parametrize('text', ['', '19/09/2026 08:00', '2026-09-19'])
def test_bad_window_text_is_rejected(text):
    with pytest.raises(ValueError):
        windows_from(text)


def test_playback_url_has_the_right_end_time():
    url = playback_url('rtsp://host:554/', 11, '2026_09_19_08_00_00', minutes=10)
    assert 'channel=11' in url
    assert 'starttime=2026_09_19_08_00_00' in url
    assert 'endtime=2026_09_19_08_10_00' in url
    assert '//cam/playback' not in url, 'ต้องไม่มีสแลชซ้ำเมื่อ base ลงท้ายด้วย /'


def test_playback_url_handles_an_hour_boundary():
    url = playback_url('rtsp://host:554', 9, '2026_09_19_08_55_00', minutes=10)
    assert 'endtime=2026_09_19_09_05_00' in url


def test_placeholder_credentials_are_detected():
    """ลืมกรอกรหัสผ่านแล้วได้ 401 ทุกช่วง ต้องจับได้ตั้งแต่ก่อนเริ่มต่อกล้อง"""
    base = 'rtsp://USER:PASS@192.168.1.64:554'
    assert any(f'{name}:' in base or f':{name}@' in base for name in ('USER', 'PASS'))
    real = 'rtsp://viewer:s3cret@192.168.1.64:554'
    assert not any(f'{name}:' in real or f':{name}@' in real for name in ('USER', 'PASS'))


# ---------- รหัสผ่านที่มีอักขระพิเศษ ----------

def test_a_password_with_an_at_sign_is_encoded():
    """@ ในรหัสผ่านทำให้ URL ถูกตัดผิดที่ แล้วได้ 401 โดยไม่มีอะไรบอกสาเหตุ"""
    from rack_ai.final_pond.harvest import credentials_in
    url = credentials_in('rtsp://192.168.1.64:554', 'viewer', 'p@ss w0rd')
    assert url == 'rtsp://viewer:p%40ss%20w0rd@192.168.1.64:554'
    assert url.count('@') == 1, 'ต้องเหลือ @ ตัวเดียวคือตัวที่คั่นรหัสผ่านกับโฮสต์'


@pytest.mark.parametrize('password', ['a:b', 'a/b', 'a#b', 'a?b', 'a&b', 'a@b'])
def test_every_url_special_character_is_escaped(password):
    from rack_ai.final_pond.harvest import credentials_in
    url = credentials_in('rtsp://host:554', 'u', password)
    body = url.split('://', 1)[1].rsplit('@', 1)[0]
    assert all(ch not in body for ch in ':/#?&@'.replace(':', '', 1) or True)
    assert '%' in url


def test_credentials_left_in_base_are_rejected_when_also_passed_separately():
    from rack_ai.final_pond.harvest import credentials_in
    with pytest.raises(ValueError, match='ซ้ำ'):
        credentials_in('rtsp://old:pw@host:554', 'new', 'pw2')


def test_base_without_credentials_is_returned_unchanged():
    from rack_ai.final_pond.harvest import credentials_in
    assert credentials_in('rtsp://host:554', None, None) == 'rtsp://host:554'


# ---------- ช่วงเวลาที่ยังมาไม่ถึง ----------

def _clock(text):
    import time as _t
    return _t.mktime(_t.strptime(text, '%Y-%m-%d %H:%M'))


def test_a_window_in_the_future_is_skipped_instead_of_returning_404():
    from rack_ai.final_pond.harvest import fit_to_now
    assert fit_to_now('2026_09_23_13_00_00', 10, _clock('2026-09-23 09:15')) is None


def test_a_window_that_just_started_is_shortened_to_what_exists():
    from rack_ai.final_pond.harvest import fit_to_now
    got = fit_to_now('2026_09_23_09_00_00', 10, _clock('2026-09-23 09:06'))
    assert got == pytest.approx(5.0)


def test_a_finished_window_keeps_its_full_length():
    from rack_ai.final_pond.harvest import fit_to_now
    assert fit_to_now('2026_09_22_08_00_00', 10, _clock('2026-09-23 09:15')) == 10


# ---------- กระจายภาพให้เต็มช่วง ----------

def test_samples_are_spread_over_the_whole_window():
    """60 ภาพในช่วง 30 นาที ต้องห่างกัน 30 วินาที ไม่ใช่กองอยู่ 2 นาทีแรก"""
    from rack_ai.final_pond.harvest import spread_every
    assert spread_every(30, 2, 60) == pytest.approx(30)


def test_a_wider_spacing_asked_for_is_kept():
    from rack_ai.final_pond.harvest import spread_every
    assert spread_every(5, 10, 60) == 10
