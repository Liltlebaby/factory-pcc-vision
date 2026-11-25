import type { SVGProps } from "react";

export type FactoryIconName =
  | "factory"
  | "overview"
  | "stations"
  | "incident"
  | "report"
  | "device"
  | "pond"
  | "conveyor"
  | "odor"
  | "scale"
  | "thermometer"
  | "camera"
  | "clock"
  | "chevron"
  | "activity"
  | "database"
  | "system"
  | "sync"
  | "refresh"
  | "check"
  | "audit"
  | "search"
  | "logout";

interface Props extends SVGProps<SVGSVGElement> {
  name: FactoryIconName;
}

export function FactoryIcon({ name, ...props }: Props) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };

  switch (name) {
    case "factory":
      return <svg {...common}><path d="M3 21V9l6 3V8l6 4V4h3v17"/><path d="M2 21h20M7 17h2m3 0h2m3 0h2"/></svg>;
    case "overview":
      return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>;
    case "stations":
      return <svg {...common}><path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11Z"/><circle cx="12" cy="10" r="2"/></svg>;
    case "incident":
      return <svg {...common}><path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4m0 3h.01"/></svg>;
    case "report":
      return <svg {...common}><path d="M4 20V10m5 10V4m5 16v-7m5 7V7"/></svg>;
    case "device":
      return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21h-4v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3.1 14H3v-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.5V3h4v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1v4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>;
    case "pond":
      return <svg {...common}><path d="M3 8h18v12H3z"/><path d="M3 13c3-2 5 2 8 0s5 2 10 0M8 3v8m8-8v8"/><path d="M6 3h4m4 0h4"/></svg>;
    case "conveyor":
      return <svg {...common}><path d="M4 8h16l2 7H2l2-7Z"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M6 15v1m12-1v1M8 11h2m4 0h2"/></svg>;
    case "odor":
      return <svg {...common}><path d="M7 20c-3-3 3-5 0-9S9 6 8 3m5 17c-3-3 3-5 0-9s2-5 1-8m5 17c-3-3 3-5 0-9"/></svg>;
    case "scale":
      return <svg {...common}><path d="M5 20h14l-1-9H6l-1 9Z"/><path d="M4 7h16M9 7V4h6v3"/><rect x="8" y="12" width="8" height="4" rx="1"/></svg>;
    case "thermometer":
      return <svg {...common}><path d="M10 14.8V5a2 2 0 1 1 4 0v9.8a4 4 0 1 1-4 0Z"/><path d="M12 8v8"/></svg>;
    case "camera":
      return <svg {...common}><path d="M14.5 6 13 4h-2L9.5 6H5a2 2 0 0 0-2 2v10h18V8a2 2 0 0 0-2-2h-4.5Z"/><circle cx="12" cy="12" r="3"/></svg>;
    case "clock":
      return <svg {...common}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
    case "chevron":
      return <svg {...common}><path d="m9 18 6-6-6-6"/></svg>;
    case "activity":
      return <svg {...common}><path d="M3 12h4l2-6 4 12 2-6h6"/></svg>;
    case "database":
      return <svg {...common}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></svg>;
    case "system":
      return <svg {...common}><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4M7 9h3l2-2 2 4 2-2h1"/></svg>;
    case "sync":
      return <svg {...common}><path d="M20 7h-5V2"/><path d="M19 7a8 8 0 1 0 1 8M4 17h5v5"/></svg>;
    case "refresh":
      return <svg {...common}><path d="M20 11a8 8 0 1 0-2.3 6M20 4v7h-7"/></svg>;
    case "check":
      return <svg {...common}><path d="m5 12 4 4L19 6"/></svg>;
    case "audit":
      return <svg {...common}><path d="M9 4H6a2 2 0 0 0-2 2v14h14v-3"/><path d="M9 2h6v4H9zM9 11h6m-6 4h4"/><circle cx="17" cy="9" r="4"/><path d="M17 7v2l1.5 1"/></svg>;
    case "search":
      return <svg {...common}><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>;
    case "logout":
      return <svg {...common}><path d="M10 5H5v14h5m4-3 4-4-4-4m4 4H9"/></svg>;
  }
}
