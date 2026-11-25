import "server-only";

import {
  persistRackAIEvents,
  rackDatabaseConfigured,
  readRackSyncCursor,
  writeRackSyncFailure,
  writeRackSyncCursor,
} from "@/lib/rack-database";
import { RACK_API, rackHeaders } from "@/lib/rack";
import { parseRackAIEventPage } from "@/lib/rack-event-contract";

const PAGE_LIMIT = 500;
const MAX_PAGES_PER_RUN = 20;

/** "rack_counted" คือชื่อปัจจุบัน ส่วน "rubber_counted" คือเหตุการณ์ที่บันทึกไว้ก่อนเปลี่ยนชื่อ */
const COUNT_EVENT_TYPES = new Set(["rack_counted", "rubber_counted"]);

export type RackSyncResult = {
  configured: boolean;
  source_cursor: number;
  events_received: number;
  pages: number;
  durable_cursor: boolean;
  caught_up: boolean;
};

export async function syncRackAIEvents(): Promise<RackSyncResult> {
  if (!rackDatabaseConfigured()) {
    return {
      configured: false,
      source_cursor: 0,
      events_received: 0,
      pages: 0,
      durable_cursor: false,
      caught_up: false,
    };
  }

  let cursor = await readRackSyncCursor();
  let eventsReceived = 0;
  let pages = 0;
  let hasMore = true;

  try {
    while (hasMore && pages < MAX_PAGES_PER_RUN) {
      const url = new URL(`${RACK_API}/api/v1/events`);
      url.searchParams.set("cursor", String(cursor));
      url.searchParams.set("limit", String(PAGE_LIMIT));
      // ไม่กรอง station_id ที่ฝั่ง rack_ai แล้ว เพราะเหตุการณ์ที่บันทึกไว้ก่อน
      // เปลี่ยนชื่อยังถูกเก็บเป็น "checker-infeed" ถ้ากรองด้วยชื่อใหม่ตัวเดียว
      // เหตุการณ์เก่าที่ยังไม่ได้ sync จะถูกข้ามไปพร้อมกับ cursor ที่เดินหน้าไปแล้ว
      const response = await fetch(url, {
        headers: rackHeaders(),
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error(`rack_event_source_failed:${response.status}`);

      const page = parseRackAIEventPage(await response.json(), cursor);
      if (page.items.length > 0) {
        const countEvents = page.items.filter((event) => COUNT_EVENT_TYPES.has(event.type));
        await persistRackAIEvents(countEvents);
        eventsReceived += countEvents.length;
        cursor = page.next_cursor;
      }
      hasMore = page.has_more;
      pages += 1;
      if (page.items.length === 0) break;
    }
  } catch (error) {
    const reason = error instanceof Error ? error.message : "rack_event_sync_failed";
    try {
      await writeRackSyncFailure(cursor, reason);
    } catch (writeError) {
      console.error("Unable to persist Vision Monitor sync failure", writeError);
    }
    throw error;
  }

  const durableCursor = await writeRackSyncCursor(cursor);
  return {
    configured: true,
    source_cursor: cursor,
    events_received: eventsReceived,
    pages,
    durable_cursor: durableCursor,
    caught_up: !hasMore,
  };
}
