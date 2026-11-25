"use client";

import { useEffect, useRef, useState } from "react";
import { RackCountReport } from "@/components/RackCountReport";
import { Metric, Panel, StatusBadge } from "@/components/ui";
import { healthOf, type RackHealth, type RackStatus } from "@/lib/rack";
import type { Status } from "@/lib/types";

/**
 * ทำไมไม่ใช้สตรีม MJPEG
 * ---------------------------------------------------------------------------
 * วัดแล้วว่าสตรีมแพงเกินไปสำหรับเครื่องนี้ ซึ่งรัน YOLO บน CPU ล้วน
 * ตัวสร้างสตรีมใน rack_ai วนทุก 50ms ต่อผู้ดูหนึ่งคน และเรียก snapshot()
 * ซึ่ง deepcopy ทั้งก้อนพร้อมจับ lock ตัวเดียวกับที่เธรด inference ต้องใช้
 * ผลคือยิ่งมีคนดู inference ยิ่งช้า — เปิดสองแท็บเหลือ 1.3 fps จากเป้า 5
 *
 * วิธีที่ใช้แทน: ถามสถานะเป็นจังหวะ แล้วดึงภาพใหม่เฉพาะตอน frame_id เปลี่ยน
 * ภาพจึงอัปเดตตามอัตราที่ inference ทำได้จริง ไม่เร็วกว่านั้น และไม่มี
 * คอนเนกชันค้างไว้ให้ service ต้องคอยป้อน
 */
const POLL_MS = 700;

const HEALTH: Record<RackHealth, { status: Status; label: string }> = {
  live: { status: "GREEN", label: "ทำงานปกติ" },
  stale: { status: "YELLOW", label: "ภาพค้าง" },
  offline: { status: "SENSOR_ERROR", label: "ไม่เชื่อมต่อ" },
};

export function RackMonitorCard() {
  const [status, setStatus] = useState<RackStatus | null>(null);
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const shownFrame = useRef(-1);

  useEffect(() => {
    let cancelled = false;

    /** โหลดภาพให้เสร็จก่อนค่อยสลับ เพื่อไม่ให้จอกะพริบเป็นช่องว่างระหว่างเฟรม */
    const swapImage = (frameId: number) => {
      const next = `/api/rack/frame?f=${frameId}`;
      const image = new Image();
      image.onload = () => {
        if (!cancelled) {
          shownFrame.current = frameId;
          setImageSrc(next);
        }
      };
      image.src = next;
    };

    const tick = async () => {
      try {
        const response = await fetch("/api/rack/status", { cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        const data = (await response.json()) as RackStatus;
        if (cancelled) return;
        setStatus(data);
        // ดึงภาพเฉพาะตอนมีเฟรมใหม่จริง ๆ ไม่ใช่ทุกรอบที่ถามสถานะ
        if (data.running && data.frame_id !== shownFrame.current) {
          swapImage(data.frame_id);
        }
      } catch {
        // service ปิดอยู่: ล้างค่าทิ้ง อย่าโชว์ตัวเลขเก่าเหมือนยังสด
        if (!cancelled) {
          setStatus(null);
          setImageSrc(null);
          shownFrame.current = -1;
        }
      }
    };

    void tick();
    const timer = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const health = healthOf(status);
  const meta = HEALTH[health];
  const inferenceFps = status?.fps.inference ?? 0;
  const lastEvent = status?.lastEvent ?? null;

  return (
    <Panel
      title="Camera 09 · นับเก๊ะออก"
      icon="🎥"
      action={<StatusBadge status={meta.status} text={meta.label} />}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_200px]">
        <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-900">
          {imageSrc ? (
            /* กรอบ เส้นนับ และยอด RACK OUT ถูกวาดมาจาก rack_ai แล้ว */
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={imageSrc}
              alt="ภาพสดจาก Camera 09 พร้อมกรอบตรวจจับเก๊ะ"
              className="block w-full"
            />
          ) : (
            <div className="flex aspect-[16/10] items-center justify-center px-6 text-center">
              <p className="text-sm text-slate-400">
                {health === "offline" ? (
                  <>
                    เชื่อมต่อ Rack Monitor ไม่ได้
                    <br />
                    <span className="text-xs text-slate-500">
                      ตรวจว่า service ที่พอร์ต 8011 ทำงานอยู่
                    </span>
                  </>
                ) : (
                  "กำลังโหลดภาพ"
                )}
              </p>
            </div>
          )}
          {health === "stale" && (
            <div className="absolute inset-x-0 bottom-0 bg-amber-500/90 px-3 py-1.5 text-center text-[11px] font-bold text-white">
              ภาพไม่อัปเดตมา {status?.result_age_seconds?.toFixed(1)} วินาที
            </div>
          )}
        </div>

        <div className="space-y-3">
          <div className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-3">
            <p className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">
              จำนวนเก๊ะออก
            </p>
            <p className="text-4xl font-bold tabular-nums text-slate-900">
              {status?.count ?? 0}
            </p>
            <p className="text-[10px] text-slate-400">ยอดสะสมของระบบ</p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Metric
              label="กล้อง"
              value={`${(status?.fps.camera ?? 0).toFixed(1)} fps`}
            />
            <Metric
              label="AI"
              value={`${inferenceFps.toFixed(1)} fps`}
              // ต่ำกว่า 5 แปลว่าเครื่องตามเป้าที่ตั้งไว้ไม่ทัน เสี่ยงนับตก
              tone={inferenceFps < 5 ? "text-amber-600" : "text-slate-900"}
              hint={inferenceFps < 5 ? "ต่ำกว่าเป้า 5" : undefined}
            />
            <Metric label="กำลังติดตาม" value={`${status?.active_tracks ?? 0} เก๊ะ`} />
            <Metric label="โมเดล" value={status?.model ?? "—"} />
          </div>

          <div className="rounded-xl border border-slate-200/70 px-3 py-2">
            <p className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">
              เหตุการณ์ล่าสุด
            </p>
            {lastEvent ? (
              <p className="text-xs text-slate-700">
                ชิ้นที่ {lastEvent.rackNumber} · ความมั่นใจ{" "}
                {(lastEvent.confidence * 100).toFixed(0)}%
              </p>
            ) : (
              <p className="text-xs text-slate-400">ยังไม่มีข้อมูล</p>
            )}
          </div>

          {status?.counter_storage_error && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-semibold text-red-700">
              บันทึกยอดลงไฟล์ไม่สำเร็จ — ยอดอาจหายเมื่อรีสตาร์ท
            </p>
          )}
        </div>
      </div>

      <RackCountReport status={status} />
    </Panel>
  );
}
