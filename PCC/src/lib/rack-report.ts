const HOUR_MS = 60 * 60 * 1000;
const BANGKOK_OFFSET_MS = 7 * HOUR_MS;
const RETENTION_MS = 7 * 24 * HOUR_MS;

export type RackCountEvent = {
  at: number;
  quantity: number;
};

export type RackReportState = {
  version: 1;
  lastCount: number | null;
  events: RackCountEvent[];
};

export type RackReportBucket = {
  start: number;
  end: number;
  label: string;
  count: number;
};

export type RackShiftBucket = RackReportBucket & {
  name: string;
  dateLabel: string;
  current: boolean;
};

export const EMPTY_RACK_REPORT: RackReportState = {
  version: 1,
  lastCount: null,
  events: [],
};

const THAI_MONTHS = [
  "ม.ค.",
  "ก.พ.",
  "มี.ค.",
  "เม.ย.",
  "พ.ค.",
  "มิ.ย.",
  "ก.ค.",
  "ส.ค.",
  "ก.ย.",
  "ต.ค.",
  "พ.ย.",
  "ธ.ค.",
];

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function bangkokDate(at: number) {
  return new Date(at + BANGKOK_OFFSET_MS);
}

function startOfBangkokHour(at: number) {
  const date = bangkokDate(at);
  return (
    Date.UTC(
      date.getUTCFullYear(),
      date.getUTCMonth(),
      date.getUTCDate(),
      date.getUTCHours(),
    ) - BANGKOK_OFFSET_MS
  );
}

function sumEvents(events: RackCountEvent[], start: number, end: number) {
  return events.reduce(
    (total, event) =>
      event.at >= start && event.at < end ? total + event.quantity : total,
    0,
  );
}

function validEvent(value: unknown): value is RackCountEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<RackCountEvent>;
  return (
    typeof event.at === "number" &&
    Number.isFinite(event.at) &&
    typeof event.quantity === "number" &&
    Number.isFinite(event.quantity) &&
    event.quantity > 0
  );
}

export function parseRackReport(value: string | null): RackReportState {
  if (!value) return EMPTY_RACK_REPORT;

  try {
    const parsed = JSON.parse(value) as Partial<RackReportState>;
    if (parsed.version !== 1 || !Array.isArray(parsed.events)) {
      return EMPTY_RACK_REPORT;
    }
    return {
      version: 1,
      lastCount:
        typeof parsed.lastCount === "number" && Number.isFinite(parsed.lastCount)
          ? Math.max(0, Math.floor(parsed.lastCount))
          : null,
      events: parsed.events.filter(validEvent),
    };
  } catch {
    return EMPTY_RACK_REPORT;
  }
}

/**
 * เปลี่ยนยอดสะสมของ service ให้เป็นเหตุการณ์สำหรับรายงาน
 * ถ้ายอดลดลงถือว่า counter ถูก reset และเริ่ม baseline ใหม่โดยไม่สร้างค่าติดลบ
 */
export function recordRackCount(
  previous: RackReportState,
  count: number,
  observedAt: number,
  lastEventAt?: number,
): RackReportState {
  const safeCount = Math.max(0, Math.floor(count));
  const cutoff = observedAt - RETENTION_MS;
  const retained = previous.events.filter((event) => event.at >= cutoff);

  if (previous.lastCount === null || safeCount <= previous.lastCount) {
    if (
      previous.lastCount === safeCount &&
      retained.length === previous.events.length
    ) {
      return previous;
    }
    return { version: 1, lastCount: safeCount, events: retained };
  }

  const eventAt =
    lastEventAt &&
    Number.isFinite(lastEventAt) &&
    lastEventAt <= observedAt + 5 * 60_000
      ? lastEventAt
      : observedAt;

  return {
    version: 1,
    lastCount: safeCount,
    events: [
      ...retained,
      { at: eventAt, quantity: safeCount - previous.lastCount },
    ],
  };
}

export function hourlyRackReport(
  events: RackCountEvent[],
  now: number,
  hours = 8,
): RackReportBucket[] {
  const currentHour = startOfBangkokHour(now);

  return Array.from({ length: hours }, (_, index) => {
    const start = currentHour - (hours - index - 1) * HOUR_MS;
    const hour = bangkokDate(start).getUTCHours();
    return {
      start,
      end: start + HOUR_MS,
      label: `${pad(hour)}:00`,
      count: sumEvents(events, start, start + HOUR_MS),
    };
  });
}

export function shiftRackReport(
  events: RackCountEvent[],
  now: number,
  shifts = 2,
): RackShiftBucket[] {
  const local = bangkokDate(now);
  const localMidnight =
    Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate()) -
    BANGKOK_OFFSET_MS;

  const candidates = Array.from({ length: 3 }, (_, dayOffset) => {
    const day = localMidnight - dayOffset * 24 * HOUR_MS;
    return [
      {
        start: day + 7 * HOUR_MS,
        end: day + 18 * HOUR_MS,
        name: "กะเช้า",
        label: "07:00–18:00",
      },
      {
        start: day + 20 * HOUR_MS,
        end: day + 32 * HOUR_MS,
        name: "กะดึก",
        label: "20:00–08:00",
      },
    ];
  })
    .flat()
    .filter((shift) => shift.start <= now)
    .sort((a, b) => b.start - a.start)
    .slice(0, shifts);

  return candidates.map((shift) => {
    const date = bangkokDate(shift.start);
    return {
      start: shift.start,
      end: shift.end,
      name: shift.name,
      label: shift.label,
      dateLabel: `${date.getUTCDate()} ${THAI_MONTHS[date.getUTCMonth()]}`,
      count: sumEvents(events, shift.start, shift.end),
      current: now >= shift.start && now < shift.end,
    };
  });
}

/** วันที่ทำงานตามเวลาไทย; กะดึกของวันที่เลือกสิ้นสุด 08:00 วันถัดไป */
export function dateShiftRackReport(
  events: RackCountEvent[],
  dateKey: string,
  now: number,
): RackShiftBucket[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) return [];
  const day = Date.parse(`${dateKey}T00:00:00+07:00`);
  if (!Number.isFinite(day)) return [];
  const date = bangkokDate(day);
  if (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}` !==
    dateKey
  ) return [];

  const dateLabel = `${date.getUTCDate()} ${THAI_MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear() + 543}`;
  return [
    { name: "กะเช้า", label: "07:00–18:00", start: day + 7 * HOUR_MS, end: day + 18 * HOUR_MS },
    { name: "กะดึก", label: "20:00–08:00 วันถัดไป", start: day + 20 * HOUR_MS, end: day + 32 * HOUR_MS },
  ].map((shift) => ({
    ...shift,
    dateLabel,
    count: sumEvents(events, shift.start, Math.min(shift.end, now)),
    current: now >= shift.start && now < shift.end,
  }));
}

export function bangkokDateKey(at: number) {
  const date = bangkokDate(at);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

/** รายชั่วโมงภายในกะ รวมชั่วโมงหลังเที่ยงคืนไว้ในกะดึกของวันเริ่มกะ */
export function hourlyShiftRackReport(
  events: RackCountEvent[],
  shift: RackShiftBucket,
  now: number,
): RackReportBucket[] {
  const hours = Math.round((shift.end - shift.start) / HOUR_MS);
  return Array.from({ length: hours }, (_, index) => {
    const start = shift.start + index * HOUR_MS;
    const end = start + HOUR_MS;
    const hour = bangkokDate(start).getUTCHours();
    return {
      start,
      end,
      label: `${pad(hour)}:00–${pad((hour + 1) % 24)}:00`,
      count: sumEvents(events, start, Math.min(end, now)),
    };
  });
}
