import unittest
from datetime import timedelta

from rack_ai.shifts import midnight
from rack_ai.tools.validate_shift_count import CountWindow, build_report, check_provenance, parse_timestamp, render_html


def day_windows(human=10, ai=10):
    start = midnight("2026-09-23") + timedelta(hours=7)
    return [CountWindow(start + timedelta(hours=i), start + timedelta(hours=i + 1), human, ai, camera_coverage_confirmed=True) for i in range(11)]


class ShiftValidationTests(unittest.TestCase):
    def test_timezone_is_required(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_timestamp("2026-09-23T07:00:00")

    def test_exact_full_shift_passes(self):
        report = build_report(
            day_windows(),
            date_key="2026-09-23",
            shift="day",
            max_total_error_pct=2,
            max_wape_pct=5,
            max_window_error=2,
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["human_total"], 110)
        self.assertEqual(report["metrics"]["wape_pct"], 0)

    def test_opposite_errors_do_not_hide_in_wape(self):
        windows = day_windows()
        windows[0] = CountWindow(windows[0].start, windows[0].end, 10, 12, camera_coverage_confirmed=True)
        windows[1] = CountWindow(windows[1].start, windows[1].end, 10, 8, camera_coverage_confirmed=True)
        report = build_report(
            windows,
            date_key="2026-09-23",
            shift="day",
            max_total_error_pct=2,
            max_wape_pct=3,
            max_window_error=2,
        )
        self.assertEqual(report["metrics"]["total_error_pct"], 0)
        self.assertGreater(report["metrics"]["wape_pct"], 3)
        self.assertFalse(report["passed"])

    def test_gap_and_overlap_fail_coverage_gate(self):
        windows = day_windows()
        windows.pop(4)
        report = build_report(
            windows,
            date_key="2026-09-23",
            shift="day",
            max_total_error_pct=2,
            max_wape_pct=5,
            max_window_error=2,
        )
        self.assertFalse(report["passed"])
        self.assertTrue(any("ขาดช่วง" in problem for problem in report["coverage_problems"]))

    def test_false_positive_in_zero_window_fails(self):
        windows = day_windows()
        windows[3] = CountWindow(windows[3].start, windows[3].end, 0, 1, camera_coverage_confirmed=True)
        report = build_report(
            windows,
            date_key="2026-09-23",
            shift="day",
            max_total_error_pct=100,
            max_wape_pct=100,
            max_window_error=5,
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["metrics"]["false_positive_windows"], 1)

    def test_empty_shift_cannot_prove_model_accuracy(self):
        report = build_report(
            day_windows(human=0, ai=0),
            date_key="2026-09-23",
            shift="day",
            max_total_error_pct=2,
            max_wape_pct=5,
            max_window_error=2,
            min_human_total=50,
        )
        self.assertFalse(report["passed"])
        sample_gate = next(gate for gate in report["gates"] if gate["key"] == "sample_size")
        self.assertFalse(sample_gate["passed"])

    def test_html_escapes_operator_notes(self):
        windows = day_windows()
        windows[0] = CountWindow(windows[0].start, windows[0].end, 10, 10, "<script>alert(1)</script>", camera_coverage_confirmed=True)
        report = build_report(
            windows,
            date_key="2026-09-23",
            shift="day",
            max_total_error_pct=2,
            max_wape_pct=5,
            max_window_error=2,
        )
        output = render_html(report)
        self.assertNotIn("<script>", output)
        self.assertIn("&lt;script&gt;", output)

    def test_unconfirmed_camera_coverage_blocks_acceptance(self):
        windows = day_windows()
        windows[4] = CountWindow(windows[4].start, windows[4].end, 10, 10)
        report = build_report(windows, date_key="2026-09-23", shift="day", max_total_error_pct=2,
                              max_wape_pct=5, max_window_error=2)
        self.assertFalse(report["passed"])
        self.assertFalse(next(gate for gate in report["gates"] if gate["key"] == "camera_coverage")["passed"])

    def test_modified_ai_count_is_rejected_by_provenance(self):
        from rack_ai.tools.export_shift_ai_counts import build_export
        from pathlib import Path
        import uuid
        model = Path(__file__).parent / f".shift-model-{uuid.uuid4().hex}.pt"
        try:
            model.write_bytes(b"weights")
            rows, provenance = build_export([], date_key="2026-09-23", shift="day",
                                            camera_id="camera-09", station_id="rack-infeed",
                                            model_path=model,
                                            exported_at=midnight("2026-09-24"))
            untouched = [CountWindow(parse_timestamp(row["window_start"]), parse_timestamp(row["window_end"]),
                                     0, row["ai_count"], camera_coverage_confirmed=True) for row in rows]
            original_report = build_report(untouched, date_key="2026-09-23", shift="day",
                                           max_total_error_pct=100, max_wape_pct=100, max_window_error=20,
                                           min_human_total=0, camera_id="camera-09")
            self.assertEqual(check_provenance(provenance, original_report, model), [])
            windows = day_windows()
            report = build_report(windows, date_key="2026-09-23", shift="day",
                                  max_total_error_pct=100, max_wape_pct=100, max_window_error=20,
                                  camera_id="camera-09")
            self.assertIn("AI counts or window timestamps changed after export",
                          check_provenance(provenance, report, model))
            self.assertEqual(rows[0]["ai_count"], 0)
        finally:
            model.unlink(missing_ok=True)

    def test_legacy_journal_model_identity_cannot_pass_provenance(self):
        from rack_ai.tools.export_shift_ai_counts import build_export
        from pathlib import Path
        import uuid
        model = Path(__file__).parent / f".shift-model-{uuid.uuid4().hex}.pt"
        try:
            model.write_bytes(b"weights")
            start = midnight("2026-09-23") + timedelta(hours=7)
            _, provenance = build_export([{
                "cursor": 1, "event_id": "event-1", "occurred_at": start.timestamp(),
                "model_version": model.name, "model_sha256": None,
            }], date_key="2026-09-23", shift="day", camera_id="camera-09",
                station_id="rack-infeed", model_path=model, exported_at=midnight("2026-09-24"))
            windows = day_windows(human=10, ai=0)
            windows[0] = CountWindow(windows[0].start, windows[0].end, 10, 1,
                                     camera_coverage_confirmed=True)
            report = build_report(windows, date_key="2026-09-23", shift="day",
                                  max_total_error_pct=100, max_wape_pct=100, max_window_error=20,
                                  camera_id="camera-09")
            self.assertIn("journal events do not prove the deployed model SHA-256",
                          check_provenance(provenance, report, model))
        finally:
            model.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
