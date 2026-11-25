import "server-only";
import type { H2sSensorStatus } from "./use-h2s-sensor";

const gatewayUrl = (process.env.H2S_GATEWAY_URL ?? "http://127.0.0.1:8022").trim();
// H2S_GATEWAY_URL=off: ไม่มีเซ็นเซอร์ H2S ติดตั้งอยู่ (บอร์ดเดิมถูกเปลี่ยนเป็นเซ็นเซอร์ pH 2026-11)
// หน้าจอจะขึ้น "ยังไม่ติดตั้ง" แทน "ไม่เชื่อมต่อ" และไม่ยิงคำขอไปหาอุปกรณ์ใด
const h2sInstalled = !/^(off|none|disabled|)$/i.test(gatewayUrl);

const NOT_INSTALLED: H2sSensorStatus = {
  online: false,
  installed: false,
  latest: null,
  history: [],
  serial: { connected: false, error: null, samples: 0 },
};

// ปลายทางที่ตั้งผิด (เช่น ชี้ไปบอร์ด pH ที่ตอบ /status คนละรูปแบบ) ต้องกลายเป็น "ติดต่อไม่ได้"
// ไม่ใช่ปล่อย JSON แปลกหน้าไปถึงหน้าจอ ซึ่งอ่าน serial.connected / latest.h2s_ppm ตรง ๆ
function isGatewayStatus(value: unknown): value is GatewayStatus {
  if (!value || typeof value !== "object") return false;
  const status = value as Partial<GatewayStatus>;
  return typeof status.online === "boolean" &&
    !!status.serial && typeof status.serial === "object" &&
    (status.latest === null || (!!status.latest && typeof status.latest.h2s_ppm === "number")) &&
    (status.history === undefined || Array.isArray(status.history));
}

// sensor-gateway (USB) ส่ง captured_at มาเอง ส่วนบอร์ด Wi-Fi ไม่มีนาฬิกาจริง ส่งแค่ age_ms
type Sample = { h2s_ppm: number; captured_at?: string; age_ms?: number };
type GatewayStatus = Omit<H2sSensorStatus, "latest" | "history"> & {
  latest: (Omit<NonNullable<H2sSensorStatus["latest"]>, "captured_at"> & { captured_at?: string }) | null;
  history?: Sample[];
};

function capturedAt(sample: { captured_at?: string; age_ms?: number }, now: number) {
  return sample.captured_at ?? new Date(now - (sample.age_ms ?? 0)).toISOString();
}

function withCapturedAt(status: GatewayStatus): H2sSensorStatus {
  const now = Date.now();
  return {
    ...status,
    latest: status.latest ? { ...status.latest, captured_at: capturedAt(status.latest, now) } : null,
    history: (status.history ?? []).map((item) => ({ h2s_ppm: item.h2s_ppm, captured_at: capturedAt(item, now) })),
  };
}

// ทุกหน้า/ทุกแท็บที่เปิด PCC poll ทุกวินาที; รวมเป็นคำขอเดียวต่อวินาทีเพื่อไม่ให้บอร์ด ESP32 รับภาระเกิน
const SHARE_WINDOW_MS = 1_000;
// Wi-Fi สัญญาณอ่อนหลุดเป็นช่วงสั้น ๆ ได้: ภายในช่วงนี้ยังแสดงค่าล่าสุดเป็น "ข้อมูลเก่า" แทน "ไม่เชื่อมต่อ"
const STALE_GRACE_MS = 30_000;

let inflight: Promise<H2sSensorStatus> | null = null;
let lastResult: { status: H2sSensorStatus; at: number } | null = null;
let lastGood: { status: H2sSensorStatus; at: number } | null = null;

async function fetchGatewayStatus(): Promise<H2sSensorStatus> {
  try {
    const response = await fetch(`${gatewayUrl}/status`, {
      cache: "no-store",
      // บอร์ด Wi-Fi ที่สัญญาณอ่อนตอบช้าได้ถึงราว 1–2 วินาที
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) throw new Error(`H2S gateway returned ${response.status}`);
    const body: unknown = await response.json();
    if (!isGatewayStatus(body)) throw new Error("ปลายทางไม่ใช่ H2S gateway — ตรวจ H2S_GATEWAY_URL");
    const status = withCapturedAt({
      ...body,
      history: (body.history ?? []).filter((item) => typeof item?.h2s_ppm === "number"),
    });
    lastGood = { status, at: Date.now() };
    return status;
  } catch (error) {
    const message = error instanceof Error ? error.message : "H2S gateway unavailable";
    const elapsed = lastGood ? Date.now() - lastGood.at : Infinity;
    if (lastGood && elapsed < STALE_GRACE_MS) {
      const { status } = lastGood;
      return {
        ...status,
        online: false,
        latest: status.latest ? { ...status.latest, age_ms: status.latest.age_ms + elapsed } : null,
        serial: { ...status.serial, connected: true, error: `ติดต่อบอร์ดไม่ได้ ${Math.round(elapsed / 1000)} วินาที (${message})` },
      };
    }
    return {
      online: false,
      latest: null,
      history: [],
      serial: { connected: false, error: message, samples: 0 },
    };
  }
}

export async function getH2sGatewayStatus(): Promise<H2sSensorStatus> {
  if (!h2sInstalled) return NOT_INSTALLED;
  if (lastResult && Date.now() - lastResult.at < SHARE_WINDOW_MS) return lastResult.status;
  inflight ??= fetchGatewayStatus().then((status) => {
    lastResult = { status, at: Date.now() };
    return status;
  }).finally(() => {
    inflight = null;
  });
  return inflight;
}
