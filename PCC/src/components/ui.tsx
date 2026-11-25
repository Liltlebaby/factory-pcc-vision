import { STATUS_META } from "@/lib/config";
import type { Status } from "@/lib/types";

export function Panel({
  title,
  icon,
  action,
  children,
  className = "",
  bodyClassName = "p-4 sm:p-5",
}: {
  title?: string;
  icon?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={`card-shadow rounded-2xl border border-slate-200/80 bg-white ${className}`}
    >
      {title && (
        <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-slate-100 px-4 py-3 sm:px-5">
          <h2 className="flex items-center gap-2 text-xs font-bold tracking-wider text-slate-700 uppercase sm:text-[13px]">
            {icon && (
              <span className="text-base leading-none" aria-hidden>
                {icon}
              </span>
            )}
            {title}
          </h2>
          {action}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function StatusBadge({
  status,
  text,
}: {
  status: Status;
  text?: string;
}) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold tracking-wide ${meta.bg} ${meta.border} ${meta.text}`}
    >
      <span className={`size-1.5 rounded-full ${meta.dot}`} />
      {text ?? meta.label}
    </span>
  );
}

export function Metric({
  label,
  value,
  hint,
  tone = "text-slate-900",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-2.5 py-2 sm:px-3">
      <p className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">
        {label}
      </p>
      <p className={`text-base font-bold tabular-nums sm:text-lg ${tone}`}>
        {value}
      </p>
      {hint && <p className="text-[10px] text-slate-400">{hint}</p>}
    </div>
  );
}

export function RuleTag({ code }: { code: string }) {
  return (
    <span className="rounded-md border border-blue-100 bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-blue-700">
      {code}
    </span>
  );
}

/** ป้ายบอกที่มาของค่า เช่น REFERENCE / SCALE */
export function Chip({
  children,
  tone = "slate",
}: {
  children: React.ReactNode;
  tone?: "slate" | "blue" | "violet";
}) {
  const tones = {
    slate: "border-slate-200 bg-slate-100 text-slate-600",
    blue: "border-blue-200 bg-blue-50 text-blue-700",
    violet: "border-violet-200 bg-violet-50 text-violet-700",
  } as const;
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
