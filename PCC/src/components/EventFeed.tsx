"use client";

import Link from "next/link";
import { STATUS_META } from "@/lib/config";
import { fmtTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Panel, RuleTag } from "./ui";

export function EventFeed() {
  const { events } = useStore();
  const recent = [...events].reverse().slice(0, 14);

  return (
    <Panel
      title="Event Log"
      icon="📡"
      action={
        <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-700">
          <span className="size-1.5 animate-pulse rounded-full bg-blue-500" />
          real-time
        </span>
      }
      bodyClassName="p-2 sm:p-3"
    >
      {recent.length === 0 ? (
        <p className="px-2 py-4 text-sm text-slate-400">
          ยังไม่มีเหตุการณ์ที่ผิดเกณฑ์ในช่วงนี้
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {recent.map((event) => (
            <li
              key={event.id}
              className="flex items-start gap-2.5 rounded-lg px-2 py-2 transition hover:bg-slate-50"
            >
              <span
                className={`mt-1.5 size-2 shrink-0 rounded-full ${STATUS_META[event.level].dot}`}
              />
              <span className="shrink-0 text-[11px] font-semibold tabular-nums text-slate-400">
                {fmtTime(event.at)}
              </span>
              <span className="min-w-0 flex-1 text-xs text-slate-700">
                {event.message}{" "}
                {event.incidentId && (
                  <Link
                    href={`/incidents/${event.incidentId}`}
                    className="font-semibold text-blue-600 hover:underline"
                  >
                    {event.incidentId}
                  </Link>
                )}
              </span>
              <span className="hidden shrink-0 sm:block">
                <RuleTag code={event.ruleCode} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
