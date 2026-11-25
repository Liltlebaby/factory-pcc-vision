import assert from "node:assert/strict";
import test from "node:test";
import { dateShiftRackReport, hourlyShiftRackReport } from "./rack-report.ts";

test("hourly shift report keeps after-midnight events in the previous workday's night shift", () => {
  const at = (value) => Date.parse(value);
  const events = [
    { at: at("2026-09-16T07:20:00+07:00"), quantity: 2 },
    { at: at("2026-09-16T20:15:00+07:00"), quantity: 3 },
    { at: at("2026-09-17T00:30:00+07:00"), quantity: 4 },
    { at: at("2026-09-17T08:00:00+07:00"), quantity: 5 },
  ];
  const now = at("2026-09-17T09:00:00+07:00");
  const [morning, night] = dateShiftRackReport(events, "2026-09-16", now);
  const morningHours = hourlyShiftRackReport(events, morning, now);
  const nightHours = hourlyShiftRackReport(events, night, now);

  assert.equal(morning.count, 2);
  assert.equal(night.count, 7);
  assert.equal(morningHours.length, 11);
  assert.equal(nightHours.length, 12);
  assert.equal(morningHours.find((hour) => hour.label === "07:00–08:00")?.count, 2);
  assert.equal(nightHours.find((hour) => hour.label === "20:00–21:00")?.count, 3);
  assert.equal(nightHours.find((hour) => hour.label === "00:00–01:00")?.count, 4);
  assert.equal(nightHours.reduce((sum, hour) => sum + hour.count, 0), night.count);
});
