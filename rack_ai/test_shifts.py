"""ตรวจว่าการแจกแจงชั่วโมงและการรวมกะไม่ทำให้ยอดหายหรือซ้ำ"""
import unittest
from datetime import datetime, timedelta

from rack_ai.shifts import BANGKOK, hourly, shifts, summarise, report_window, today_key


def at(date_key, hour, minute=0):
    base = datetime.strptime(date_key, '%Y-%m-%d').replace(tzinfo=BANGKOK)
    return (base + timedelta(hours=hour, minutes=minute)).timestamp()


class WindowTests(unittest.TestCase):
    def test_report_day_runs_from_0700_to_0800_next_day(self):
        start, end = report_window('2026-09-21')
        self.assertEqual(start, at('2026-09-21', 7))
        self.assertEqual(end, at('2026-09-22', 8))
        self.assertEqual((end - start) / 3600, 25)

    def test_before_0700_still_belongs_to_yesterdays_report(self):
        self.assertEqual(today_key(at('2026-09-21', 3)), '2026-09-20')
        self.assertEqual(today_key(at('2026-09-21', 7)), '2026-09-21')
        self.assertEqual(today_key(at('2026-09-21', 23)), '2026-09-21')


class BucketTests(unittest.TestCase):
    def test_every_hour_lands_in_exactly_one_shift(self):
        buckets = hourly([], '2026-09-21')
        self.assertEqual(len(buckets), 25)
        groups = shifts(buckets)
        self.assertEqual([g['hours'] for g in groups], [11, 2, 12])
        self.assertEqual(sum(g['hours'] for g in groups), len(buckets))

    def test_totals_never_lose_or_duplicate_a_count(self):
        # หนึ่งครั้งในทุกชั่วโมงของวันรายงาน
        stamps = [at('2026-09-21', 7 + i, 30) for i in range(25)]
        result = summarise(stamps, '2026-09-21', now=at('2026-09-22', 9))
        self.assertEqual(result['total'], 25)
        self.assertEqual(sum(g['count'] for g in result['shifts']), 25)
        self.assertEqual([g['count'] for g in result['shifts']], [11, 2, 12])

    def test_the_unassigned_evening_hours_are_visible_not_dropped(self):
        stamps = [at('2026-09-21', 18, 10), at('2026-09-21', 19, 50)]
        result = summarise(stamps, '2026-09-21', now=at('2026-09-22', 9))
        outside = [g for g in result['shifts'] if g['key'] == 'outside'][0]
        self.assertEqual(outside['count'], 2)
        self.assertEqual(result['total'], 2)

    def test_night_hours_after_midnight_are_marked_next_day(self):
        buckets = hourly([at('2026-09-22', 2)], '2026-09-21')
        two_am = [b for b in buckets if b['label'] == '02:00'][0]
        self.assertTrue(two_am['next_day'])
        self.assertEqual(two_am['count'], 1)

    def test_events_outside_the_report_day_are_ignored(self):
        stamps = [at('2026-09-21', 6), at('2026-09-22', 9)]
        self.assertEqual(summarise(stamps, '2026-09-21')['total'], 0)

    def test_pending_hours_differ_from_hours_that_counted_zero(self):
        result = summarise([], '2026-09-21', now=at('2026-09-21', 12, 30))
        by_label = {b['label']: b for b in result['hours']}
        self.assertFalse(by_label['08:00']['pending'], 'ผ่านมาแล้วและนับได้ศูนย์')
        self.assertTrue(by_label['16:00']['pending'], 'ยังไม่ถึงเวลา')

    def test_current_shift_is_flagged(self):
        result = summarise([], '2026-09-21', now=at('2026-09-21', 22))
        current = [g['key'] for g in result['shifts'] if g['current']]
        self.assertEqual(current, ['night'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
