"use client";

import { useEffect, useState } from "react";

export type H2sSensorStatus = {
  online: boolean;
  /** false เมื่อปิดใช้ H2S ไว้ (H2S_GATEWAY_URL=off) — หน้าจอแสดง "ยังไม่ติดตั้ง" */
  installed?: boolean;
  latest: {
    h2s_ppm: number;
    device_id: string;
    quality: string;
    captured_at: string;
    age_ms: number;
  } | null;
  history: Array<{ h2s_ppm: number; captured_at: string }>;
  serial: { connected: boolean; error: string | null; samples: number };
};

const EMPTY_STATUS: H2sSensorStatus = {
  online: false,
  latest: null,
  history: [],
  serial: { connected: false, error: null, samples: 0 },
};

export function useH2sSensor(intervalMs = 1_000) {
  const [status, setStatus] = useState<H2sSensorStatus>(EMPTY_STATUS);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/sensors/h2s/status", { cache: "no-store" });
        const next = await response.json() as H2sSensorStatus;
        if (active) setStatus(next);
      } catch {
        if (active) setStatus((current) => ({ ...current, online: false }));
      }
    };
    void load();
    const timer = window.setInterval(load, intervalMs);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [intervalMs]);

  return status;
}
