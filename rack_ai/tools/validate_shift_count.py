"""สร้างรายงานตรวจรับยอดนับเก๊ะหนึ่งกะจากยอด AI เทียบกับยอดคน

ตัวอย่าง::

    python -m rack_ai.tools.validate_shift_count ^
      --input docs/templates/rack-shift-validation.example.csv ^
      --date 2026-09-23 --shift day --model models/best_v3.pt ^
      --camera-id camera-09 --reviewer "ชื่อผู้ตรวจ" ^
      --html output/rack-validation-2026-09-23-day.html ^
      --json output/rack-validation-2026-09-23-day.json

ค่าเกณฑ์เริ่มต้นเป็นเกณฑ์ทดลองทางวิศวกรรม ไม่ใช่มาตรฐานที่ QC อนุมัติแล้ว
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from rack_ai.shifts import BANGKOK, DAY_END_HOUR, DAY_START_HOUR, NIGHT_END_HOUR, NIGHT_START_HOUR, midnight


SHIFT_LABELS = {"day": "กะเช้า", "night": "กะดึก"}


@dataclass(frozen=True)
class CountWindow:
    start: datetime
    end: datetime
    human_count: int
    ai_count: int
    notes: str = ""
    camera_coverage_confirmed: bool | None = None

    @property
    def delta(self) -> int:
        return self.ai_count - self.human_count

    @property
    def absolute_error(self) -> int:
        return abs(self.delta)


def parse_timestamp(raw: str) -> datetime:
    value = raw.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO timestamp: {raw}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"timestamp must include timezone offset: {raw}")
    return result.astimezone(BANGKOK)


def _count(raw: str, field: str, row_number: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number}: {field} must be an integer") from exc
    if value < 0:
        raise ValueError(f"row {row_number}: {field} cannot be negative")
    return value


def _coverage(raw: str, row_number: int) -> bool | None:
    value = (raw or "").strip().casefold()
    if value in {"yes", "true", "1"}:
        return True
    if value in {"no", "false", "0"}:
        return False
    if not value:
        return None
    raise ValueError(f"row {row_number}: camera_coverage_confirmed must be yes or no")


def load_windows(path: Path) -> list[CountWindow]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"window_start", "window_end", "human_count", "ai_count", "camera_coverage_confirmed"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"CSV missing column(s): {', '.join(missing)}")
        windows = []
        for row_number, row in enumerate(reader, 2):
            start = parse_timestamp(row["window_start"])
            end = parse_timestamp(row["window_end"])
            if end <= start:
                raise ValueError(f"row {row_number}: window_end must be after window_start")
            windows.append(
                CountWindow(
                    start=start,
                    end=end,
                    human_count=_count(row["human_count"], "human_count", row_number),
                    ai_count=_count(row["ai_count"], "ai_count", row_number),
                    notes=(row.get("notes") or "").strip(),
                    camera_coverage_confirmed=_coverage(row["camera_coverage_confirmed"], row_number),
                )
            )
    if not windows:
        raise ValueError("CSV contains no count windows")
    return windows


def expected_shift_window(date_key: str, shift: str) -> tuple[datetime, datetime]:
    base = midnight(date_key)
    if shift == "day":
        return base + timedelta(hours=DAY_START_HOUR), base + timedelta(hours=DAY_END_HOUR)
    if shift == "night":
        return base + timedelta(hours=NIGHT_START_HOUR), base + timedelta(hours=NIGHT_END_HOUR)
    raise ValueError(f"unknown shift: {shift}")


def validate_windows(
    windows: Iterable[CountWindow],
    expected_start: datetime,
    expected_end: datetime,
    *,
    require_full_coverage: bool = True,
) -> list[str]:
    ordered = sorted(windows, key=lambda item: item.start)
    problems: list[str] = []
    if not ordered:
        return ["ไม่มีข้อมูลช่วงเวลา"]
    for previous, current in zip(ordered, ordered[1:]):
        if current.start < previous.end:
            problems.append(
                f"ช่วงเวลาซ้อนกัน: {previous.start.isoformat()} ถึง {previous.end.isoformat()} "
                f"กับ {current.start.isoformat()} ถึง {current.end.isoformat()}"
            )
        elif require_full_coverage and current.start > previous.end:
            problems.append(f"ข้อมูลขาดช่วง: {previous.end.isoformat()} ถึง {current.start.isoformat()}")
    if any(item.start < expected_start or item.end > expected_end for item in ordered):
        problems.append("มีข้อมูลอยู่นอกช่วงกะที่เลือก")
    if require_full_coverage:
        if ordered[0].start != expected_start:
            problems.append(f"เวลาเริ่มไม่ครบกะ ต้องเริ่ม {expected_start.isoformat()}")
        if ordered[-1].end != expected_end:
            problems.append(f"เวลาสิ้นสุดไม่ครบกะ ต้องจบ {expected_end.isoformat()}")
    return problems


def build_report(
    windows: Iterable[CountWindow],
    *,
    date_key: str,
    shift: str,
    max_total_error_pct: float,
    max_wape_pct: float,
    max_window_error: int,
    min_human_total: int = 50,
    require_full_coverage: bool = True,
    model_name: str = "ไม่ระบุ",
    model_sha256: str = "ไม่ระบุ",
    camera_id: str = "camera-09",
    reviewer: str = "ไม่ระบุ",
) -> dict:
    ordered = sorted(windows, key=lambda item: item.start)
    expected_start, expected_end = expected_shift_window(date_key, shift)
    problems = validate_windows(
        ordered,
        expected_start,
        expected_end,
        require_full_coverage=require_full_coverage,
    )
    human_total = sum(item.human_count for item in ordered)
    ai_total = sum(item.ai_count for item in ordered)
    signed_delta = ai_total - human_total
    absolute_total_error = abs(signed_delta)
    sum_absolute_window_errors = sum(item.absolute_error for item in ordered)
    total_error_pct = 100 * absolute_total_error / human_total if human_total else (0.0 if ai_total == 0 else math.inf)
    wape_pct = 100 * sum_absolute_window_errors / human_total if human_total else (0.0 if ai_total == 0 else math.inf)
    max_observed_window_error = max((item.absolute_error for item in ordered), default=0)
    exact_windows = sum(item.absolute_error == 0 for item in ordered)
    false_positive_windows = sum(item.human_count == 0 and item.ai_count > 0 for item in ordered)

    gates = [
        {"key": "coverage", "label": "ข้อมูลครบช่วงกะและไม่ซ้อน", "passed": not problems},
        {
            "key": "camera_coverage",
            "label": "ผู้ตรวจยืนยันภาพกล้องครบทุกช่วง",
            "passed": bool(ordered) and all(item.camera_coverage_confirmed is True for item in ordered),
            "actual": sum(item.camera_coverage_confirmed is True for item in ordered),
        },
        {
            "key": "sample_size",
            "label": f"ยอดอ้างอิงจากคนอย่างน้อย {min_human_total} เก๊ะ",
            "passed": human_total >= min_human_total,
            "actual": human_total,
        },
        {
            "key": "total_error",
            "label": f"Total Error ≤ {max_total_error_pct:g}%",
            "passed": total_error_pct <= max_total_error_pct,
            "actual": total_error_pct,
        },
        {
            "key": "wape",
            "label": f"WAPE ≤ {max_wape_pct:g}%",
            "passed": wape_pct <= max_wape_pct,
            "actual": wape_pct,
        },
        {
            "key": "window_error",
            "label": f"ผิดพลาดต่อช่วงไม่เกิน {max_window_error} เก๊ะ",
            "passed": max_observed_window_error <= max_window_error,
            "actual": max_observed_window_error,
        },
        {
            "key": "false_positive",
            "label": "ไม่มีการนับในช่วงที่คนยืนยันว่าเป็นศูนย์",
            "passed": false_positive_windows == 0,
            "actual": false_positive_windows,
        },
    ]
    passed = all(gate["passed"] for gate in gates)
    return {
        "schema_version": 1,
        "date": date_key,
        "shift": shift,
        "shift_label": SHIFT_LABELS[shift],
        "shift_time_label": "07:00–18:00" if shift == "day" else "20:00–08:00 วันถัดไป",
        "camera_id": camera_id,
        "reviewer": reviewer,
        "model": {"name": model_name, "sha256": model_sha256},
        "expected_start": expected_start.isoformat(),
        "expected_end": expected_end.isoformat(),
        "full_coverage_required": require_full_coverage,
        "passed": passed,
        "metrics": {
            "human_total": human_total,
            "ai_total": ai_total,
            "signed_delta": signed_delta,
            "absolute_total_error": absolute_total_error,
            "total_error_pct": round(total_error_pct, 3),
            "wape_pct": round(wape_pct, 3),
            "mean_absolute_error_per_window": round(sum_absolute_window_errors / len(ordered), 3),
            "max_window_error": max_observed_window_error,
            "exact_windows": exact_windows,
            "window_count": len(ordered),
            "false_positive_windows": false_positive_windows,
        },
        "thresholds": {
            "max_total_error_pct": max_total_error_pct,
            "max_wape_pct": max_wape_pct,
            "max_window_error": max_window_error,
            "min_human_total": min_human_total,
        },
        "gates": gates,
        "coverage_problems": problems,
        "windows": [
            {
                "window_start": item.start.isoformat(),
                "window_end": item.end.isoformat(),
                "human_count": item.human_count,
                "ai_count": item.ai_count,
                "delta": item.delta,
                "absolute_error": item.absolute_error,
                "notes": item.notes,
                "camera_coverage_confirmed": item.camera_coverage_confirmed,
            }
            for item in ordered
        ],
        "notice": "เกณฑ์ในรายงานเป็นค่าเริ่มต้นทางวิศวกรรม ต้องให้ QC และ Production อนุมัติก่อนใช้ตัดสิน Production",
    }


def _number(value: float) -> str:
    return "∞" if math.isinf(value) else f"{value:,.2f}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ai_series_sha256(entries: Iterable[tuple[str, str, int]]) -> str:
    digest = hashlib.sha256()
    for start, end, count in entries:
        digest.update(f"{start}|{end}|{count}\n".encode("utf-8"))
    return digest.hexdigest()


def check_provenance(provenance: dict, report: dict, model_path: Path) -> list[str]:
    problems = []
    for key in ("date", "shift", "camera_id"):
        if provenance.get(key) != report.get(key):
            problems.append(f"provenance {key} does not match report")
    if provenance.get("model_sha256_at_export") != file_sha256(model_path):
        problems.append("model file differs from export")
    if provenance.get("model_file") != model_path.name:
        problems.append("model filename differs from export")
    if provenance.get("shift_complete") is not True:
        problems.append("AI export was created before the shift ended")
    expected_digest = ai_series_sha256(
        (item["window_start"], item["window_end"], item["ai_count"])
        for item in report["windows"]
    )
    if provenance.get("ai_series_sha256") != expected_digest:
        problems.append("AI counts or window timestamps changed after export")
    if provenance.get("ai_total") != report["metrics"]["ai_total"]:
        problems.append("AI total differs from export")
    if provenance.get("event_count") != report["metrics"]["ai_total"]:
        problems.append("selected journal events do not match AI total")
    if provenance.get("event_count", 0) > 0 and provenance.get("model_identity_verified") is not True:
        problems.append("journal events do not prove the deployed model SHA-256")
    return problems


def render_html(report: dict) -> str:
    status_class = "pass" if report["passed"] else "fail"
    status_text = "ผ่านเกณฑ์ทดลอง" if report["passed"] else "ยังไม่ผ่านเกณฑ์"
    metrics = report["metrics"]
    max_count = max(
        [1] + [max(item["human_count"], item["ai_count"]) for item in report["windows"]]
    )
    gate_cards = "".join(
        f'<li class="gate {"ok" if gate["passed"] else "bad"}">'
        f'<span>{"✓" if gate["passed"] else "×"}</span>{html.escape(gate["label"])}</li>'
        for gate in report["gates"]
    )
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(datetime.fromisoformat(item['window_start']).strftime('%H:%M'))}–"
        f"{html.escape(datetime.fromisoformat(item['window_end']).strftime('%H:%M'))}</td>"
        f"<td>{item['human_count']}</td><td>{item['ai_count']}</td>"
        f"<td>{'ยืนยัน' if item['camera_coverage_confirmed'] is True else 'ยังไม่ยืนยัน'}</td>"
        f"<td class=\"{'positive' if item['delta'] > 0 else 'negative' if item['delta'] < 0 else ''}\">{item['delta']:+d}</td>"
        "<td><div class=\"bars\">"
        f"<i class=\"human\" style=\"width:{100 * item['human_count'] / max_count:.1f}%\"></i>"
        f"<i class=\"ai\" style=\"width:{100 * item['ai_count'] / max_count:.1f}%\"></i>"
        "</div></td>"
        f"<td>{html.escape(item['notes'])}</td></tr>"
        for item in report["windows"]
    )
    issues = report["coverage_problems"] + report.get("provenance_problems", [])
    problems = "" if not issues else (
        '<section class="problems"><h2>ข้อมูลที่ต้องตรวจเพิ่มเติม</h2><ul>'
        + "".join(f"<li>{html.escape(problem)}</li>" for problem in issues)
        + "</ul></section>"
    )
    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>รายงานตรวจรับยอดนับเก๊ะ {html.escape(report['date'])}</title>
<style>
:root{{--ink:#14213d;--muted:#6b7a99;--line:#dfe7f3;--blue:#176bff;--cyan:#00b8d9;--green:#079669;--red:#e03c4f;--surface:#fff}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#eef5ff,#f8fbff 45%,#edfdf8);color:var(--ink);font-family:"Segoe UI",Tahoma,sans-serif}}
main{{max-width:1120px;margin:auto;padding:36px 22px 56px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:24px}}
.eyebrow{{color:var(--blue);font-weight:800;letter-spacing:.12em;font-size:12px}}h1{{font-size:34px;margin:8px 0}}p{{color:var(--muted);margin:5px 0}}
.badge{{padding:10px 16px;border-radius:999px;font-weight:800;white-space:nowrap}}.badge.pass{{color:#067a54;background:#dff9ef}}.badge.fail{{color:#b42335;background:#ffe6e9}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}}.card,.panel,.problems{{background:rgba(255,255,255,.95);border:1px solid var(--line);box-shadow:0 12px 35px rgba(55,84,135,.09);border-radius:18px}}
.card{{padding:20px}}.card small{{display:block;color:var(--muted);font-weight:700}}.card strong{{display:block;font-size:31px;margin-top:7px}}.card em{{font-style:normal;color:var(--muted);font-size:13px}}
.panel{{padding:22px;margin-top:18px}}h2{{font-size:18px;margin:0 0 16px}}.gates{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;padding:0;list-style:none}}.gate{{padding:12px;border-radius:12px;background:#f5f8fd;font-weight:650}}.gate span{{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;margin-right:9px}}.gate.ok span{{background:#dff9ef;color:var(--green)}}.gate.bad span{{background:#ffe6e9;color:var(--red)}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left}}th{{font-size:12px;color:var(--muted);text-transform:uppercase}}td:nth-child(2),td:nth-child(3),td:nth-child(5){{font-weight:750}}.positive{{color:var(--red)}}.negative{{color:#ce7d00}}
.bars{{width:180px}}.bars i{{display:block;height:6px;border-radius:8px;margin:3px 0}}.human{{background:var(--cyan)}}.ai{{background:var(--blue)}}.legend{{display:flex;gap:15px;font-size:12px;color:var(--muted)}}.legend i{{display:inline-block;width:11px;height:5px;border-radius:3px;margin-right:5px}}
.problems{{padding:20px;margin-top:18px;border-color:#ffc9cf;background:#fff7f8}}.problems h2{{color:var(--red)}}footer{{margin-top:22px;padding:14px;color:var(--muted);font-size:12px}}
@media(max-width:760px){{header{{display:block}}.badge{{display:inline-block;margin-top:14px}}.cards{{grid-template-columns:repeat(2,1fr)}}.gates{{grid-template-columns:1fr}}.panel{{overflow-x:auto}}table{{min-width:760px}}}}
</style></head><body><main>
<header><div><div class="eyebrow">RACK MONITOR · ACCEPTANCE REPORT</div><h1>ตรวจรับยอดนับเก๊ะรายกะ</h1><p>{html.escape(report['date'])} · {html.escape(report['shift_label'])} · {html.escape(report['shift_time_label'])}</p><p>กล้อง {html.escape(report['camera_id'])} · โมเดล {html.escape(report['model']['name'])} · SHA-256 {html.escape(report['model']['sha256'][:12])}… · ผู้ตรวจ {html.escape(report['reviewer'])}</p></div><div class="badge {status_class}">{status_text}</div></header>
<section class="cards"><article class="card"><small>คนนับ</small><strong>{metrics['human_total']:,}</strong><em>เก๊ะ</em></article><article class="card"><small>AI นับ</small><strong>{metrics['ai_total']:,}</strong><em>เก๊ะ</em></article><article class="card"><small>Total Error</small><strong>{_number(metrics['total_error_pct'])}%</strong><em>ต่าง {metrics['signed_delta']:+d} เก๊ะ</em></article><article class="card"><small>WAPE รายช่วง</small><strong>{_number(metrics['wape_pct'])}%</strong><em>ตรงทั้งหมด {metrics['exact_windows']}/{metrics['window_count']} ช่วง</em></article></section>
<section class="panel"><h2>เงื่อนไขตรวจรับ</h2><ul class="gates">{gate_cards}</ul></section>
{problems}
<section class="panel"><h2>ผลเทียบรายช่วง</h2><div class="legend"><span><i class="human"></i>คนนับ</span><span><i class="ai"></i>AI</span></div><table><thead><tr><th>ช่วงเวลา</th><th>คน</th><th>AI</th><th>ภาพกล้อง</th><th>ต่าง</th><th>สัดส่วน</th><th>หมายเหตุ</th></tr></thead><tbody>{rows}</tbody></table></section>
<footer>{html.escape(report['notice'])}</footer></main></body></html>"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help="CSV ยอดคนและ AI รายช่วง")
    parser.add_argument("--date", required=True, help="วันรายงาน YYYY-MM-DD")
    parser.add_argument("--shift", choices=sorted(SHIFT_LABELS), required=True)
    parser.add_argument("--model", type=Path, required=True, help="ไฟล์ .pt ที่ใช้สร้างยอด AI")
    parser.add_argument("--provenance", type=Path, default=None, help="หลักฐานจาก export_shift_ai_counts สำหรับตรวจรับจริง")
    parser.add_argument("--camera-id", default="camera-09")
    parser.add_argument("--reviewer", required=True, help="ชื่อผู้ตรวจนับหรือผู้รับรองข้อมูล")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--html", type=Path, default=None)
    parser.add_argument("--max-total-error-pct", type=float, default=2.0)
    parser.add_argument("--max-wape-pct", type=float, default=5.0)
    parser.add_argument("--max-window-error", type=int, default=2)
    parser.add_argument("--min-human-total", type=int, default=50)
    parser.add_argument("--allow-partial", action="store_true", help="ทดลองบางช่วงโดยไม่บังคับครบทั้งกะ")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if not args.model.is_file() or args.model.suffix.casefold() != ".pt":
            raise ValueError(f"model must be an existing .pt file: {args.model}")
        windows = load_windows(args.input)
        report = build_report(
            windows,
            date_key=args.date,
            shift=args.shift,
            max_total_error_pct=args.max_total_error_pct,
            max_wape_pct=args.max_wape_pct,
            max_window_error=args.max_window_error,
            min_human_total=args.min_human_total,
            require_full_coverage=not args.allow_partial,
            model_name=args.model.name,
            model_sha256=file_sha256(args.model),
            camera_id=args.camera_id,
            reviewer=args.reviewer,
        )
        if args.provenance:
            provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
            if not isinstance(provenance, dict):
                raise ValueError("provenance must be a JSON object")
            provenance_problems = check_provenance(provenance, report, args.model)
            report["gates"].append({
                "key": "journal_provenance", "label": "ยอด AI ตรงกับ Event Journal และกะสิ้นสุดแล้ว",
                "passed": not provenance_problems,
            })
            report["provenance_problems"] = provenance_problems
            report["passed"] = report["passed"] and not provenance_problems
        else:
            report["provenance_problems"] = ["ไม่ได้แนบหลักฐาน Event Journal; ผลนี้เป็นการทดลองเท่านั้น"]
            report["gates"].append({
                "key": "journal_provenance", "label": "ยอด AI มีหลักฐานจาก Event Journal",
                "passed": False,
            })
            report["passed"] = False
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(report), encoding="utf-8")

    metrics = report["metrics"]
    print(f"{report['date']} {report['shift_label']}: คน={metrics['human_total']} AI={metrics['ai_total']}")
    print(f"Total Error={_number(metrics['total_error_pct'])}% WAPE={_number(metrics['wape_pct'])}%")
    print("PASS" if report["passed"] else "NOT PASSED")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
