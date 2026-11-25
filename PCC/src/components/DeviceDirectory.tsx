import Link from "next/link";
import { FactoryIcon, type FactoryIconName } from "./FactoryIcon";
import { DataStatus, type DataState } from "./StatusMark";
import type { StationAIStatus } from "@/lib/rack";
import type { StationTelemetry } from "@/lib/telemetry";
import type { H2sSensorStatus } from "@/lib/use-h2s-sensor";
import { h2sDataState } from "@/lib/h2s-state";

type Readiness = "READY" | "PARTIAL" | "WAITING" | "BLOCKED";

type IntegrationItem = {
  id: string;
  name: string;
  point: string;
  interface: string;
  state: DataState;
  readiness: Readiness;
  icon: FactoryIconName;
  note: string;
  next: string;
  href: string;
};

const READINESS: Record<Readiness, { label: string; classes: string; percent: number }> = {
  READY: { label: "พร้อมเชื่อมใช้งาน", classes: "bg-emerald-50 text-emerald-700 ring-emerald-200", percent: 100 },
  PARTIAL: { label: "ซอฟต์แวร์พร้อม", classes: "bg-blue-50 text-blue-700 ring-blue-200", percent: 70 },
  WAITING: { label: "รออุปกรณ์จริง", classes: "bg-amber-50 text-amber-700 ring-amber-200", percent: 45 },
  BLOCKED: { label: "รอยืนยันสเปก", classes: "bg-slate-100 text-slate-600 ring-slate-200", percent: 20 },
};

function dataState(status?: StationTelemetry["data_status"]): DataState {
  if (status === "live") return "LIVE";
  if (status === "stale") return "STALE";
  if (status === "demo") return "DEMO";
  return "OFFLINE";
}

function ReadinessPill({ value }: { value: Readiness }) {
  const item = READINESS[value];
  return <span className={`inline-flex w-fit items-center rounded-full px-2.5 py-1 text-[10px] font-black ring-1 ${item.classes}`}>{item.label}</span>;
}

export function DeviceDirectory({
  visionStatus = null,
  telemetry = {},
  h2sStatus = null,
}: {
  visionStatus?: StationAIStatus | null;
  telemetry?: Record<string, StationTelemetry>;
  h2sStatus?: H2sSensorStatus | null;
}) {
  const h2sState: DataState = h2sDataState(h2sStatus);
  const camera = visionStatus?.cameras[0];
  const task = camera?.tasks.find((item) => item.task_id === "rack-counting" || item.task_id === "rubber-counting") ?? camera?.tasks[0];
  const visionState: DataState = !visionStatus
    ? "OFFLINE"
    : visionStatus.data_status === "live"
      ? "LIVE"
      : visionStatus.data_status === "not_installed" ? "NOT_INSTALLED" : "OFFLINE";

  const integrations: IntegrationItem[] = [
    {
      id: "vision-monitor",
      name: "Vision Monitor · Camera 09",
      point: "หอโรยยาง · นับเก๊ะเข้าเตา",
      interface: "REST + Cursor Event API",
      state: visionState,
      readiness: camera ? "READY" : "PARTIAL",
      icon: "camera",
      note: camera ? `${camera.camera_status} · โมเดล ${task?.model_version ?? "—"}` : "API และหน้า PCC พร้อม รอการเชื่อมบริการ/RTSP",
      next: camera ? "ตรวจยอดเทียบคนหนึ่งกะเต็ม" : "เปิด Vision Monitor และตรวจ RTSP Camera 09",
      href: "/stations/rack-infeed",
    },
    {
      id: "final-pond",
      name: "Temperature + pH Gateway",
      point: "บ่อสุดท้าย",
      interface: "ESP32 / RS-485 → HTTP API",
      state: dataState(telemetry["final-pond"]?.data_status) === "OFFLINE" ? "DEMO" : dataState(telemetry["final-pond"]?.data_status),
      readiness: "WAITING",
      icon: "pond",
      note: "API, schema, rule engine และหน้าจอพร้อมแล้ว",
      next: "ติดตั้งหัววัด ทำ calibration และส่ง telemetry จริง",
      href: "/stations/final-pond",
    },
    {
      id: "rubber-scale",
      name: "Rubber Scale Gateway",
      point: "ตาชั่งน้ำหนักยาง",
      interface: "Serial / Modbus / HTTP API",
      state: dataState(telemetry["rubber-scale"]?.data_status) === "OFFLINE" ? "DEMO" : dataState(telemetry["rubber-scale"]?.data_status),
      readiness: "WAITING",
      icon: "scale",
      note: "หน้าจอและ metric rubber_weight พร้อมรับข้อมูล",
      next: "ยืนยัน protocol รุ่นตาชั่งและติดตั้ง gateway",
      href: "/stations/rubber-scale",
    },
    {
      id: "furnace-temperature",
      name: "Furnace Temperature Gateway",
      point: "อุณหภูมิเตา LINE-1",
      interface: "Recorder / Sensor → HTTP API",
      state: dataState(telemetry["furnace-temperature"]?.data_status) === "OFFLINE" ? "DEMO" : dataState(telemetry["furnace-temperature"]?.data_status),
      readiness: "WAITING",
      icon: "thermometer",
      note: "รองรับ Digital Thermometer, Burner และ Recorder",
      next: "ยืนยัน protocol และ mapping ทั้ง 3 ช่องสัญญาณ",
      href: "/stations/furnace-temperature",
    },
    {
      id: "rubber-odor",
      name: "H₂S Sensor · SN-3002-H2S-N01",
      point: "จุดตรวจกลิ่นเหม็นของยาง",
      interface: "ESP32 / RS-485 Modbus → Serial Gateway",
      state: h2sState,
      readiness: h2sStatus?.installed === false ? "WAITING" : h2sStatus?.online ? "READY" : "PARTIAL",
      icon: "odor",
      note: h2sStatus?.installed === false
        ? "ปิดใช้งาน — บอร์ดเดิมเปลี่ยนไปวัด pH บ่อสุดท้าย"
        : h2sStatus?.latest ? `ล่าสุด ${h2sStatus.latest.h2s_ppm.toFixed(1)} ppm · เกณฑ์ 0.5 / 1 / 5 / 10 ppm` : `Gateway ไม่ตอบ${h2sStatus?.serial.error ? ` (${h2sStatus.serial.error})` : ""}`,
      next: h2sStatus?.installed === false
        ? "ติดตั้งบอร์ด H₂S ชุดใหม่ แล้วตั้ง H2S_GATEWAY_URL"
        : h2sStatus?.online ? "ทดสอบกับแหล่ง H₂S จริงและตั้งการแจ้งเตือน" : "ตรวจ ESP32 / Serial Gateway พอร์ต 8022",
      href: "/stations/rubber-odor",
    },
  ];

  const live = integrations.filter((item) => item.state === "LIVE").length;
  const waiting = integrations.filter((item) => item.readiness === "WAITING").length;
  const score = Math.round(integrations.reduce((sum, item) => sum + READINESS[item.readiness].percent, 0) / integrations.length);

  return <div className="space-y-5">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div><p className="text-xs font-black uppercase tracking-[0.16em] text-blue-700">Devices & integrations</p><h1 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">อุปกรณ์และความพร้อมรายจุด</h1><p className="mt-1 text-sm text-slate-500">แยกความพร้อมของซอฟต์แวร์ อุปกรณ์จริง และสถานะข้อมูล เพื่อรู้ว่าต้องดำเนินการจุดใดต่อ</p></div>
      <Link href="/system" className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 text-xs font-black text-white transition hover:bg-slate-800"><FactoryIcon name="system" className="size-4" />ตรวจสถานะบริการ</Link>
    </header>

    <section className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-[10px] font-black uppercase tracking-wider text-slate-400">Integration readiness</p><div className="mt-2 flex items-end justify-between"><strong className="text-3xl font-black tabular-nums text-slate-950">{score}%</strong><span className="text-xs font-bold text-blue-700">{integrations.length} จุด</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-blue-600 to-cyan-400" style={{ width: `${score}%` }} /></div></div>
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-[10px] font-black uppercase tracking-wider text-slate-400">ข้อมูลจริงขณะนี้</p><div className="mt-2 flex items-end justify-between"><strong className="text-3xl font-black tabular-nums text-slate-950">{live}</strong><span className="text-xs font-bold text-emerald-700">LIVE</span></div><p className="mt-3 text-[11px] text-slate-500">จุดที่กำลังส่งข้อมูลจริงเข้าสู่ระบบ</p></div>
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-[10px] font-black uppercase tracking-wider text-slate-400">รอหน้างาน</p><div className="mt-2 flex items-end justify-between"><strong className="text-3xl font-black tabular-nums text-slate-950">{waiting}</strong><span className="text-xs font-bold text-amber-700">จุด</span></div><p className="mt-3 text-[11px] text-slate-500">ซอฟต์แวร์พร้อม แต่ยังรอ sensor/gateway จริง</p></div>
    </section>

    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="hidden grid-cols-[1.35fr_1fr_0.9fr_0.75fr_1.3fr] gap-4 border-b border-slate-100 bg-slate-50 px-5 py-3 text-[10px] font-black uppercase tracking-wider text-slate-400 lg:grid"><span>อุปกรณ์ / บริการ</span><span>จุดงาน</span><span>การเชื่อมต่อ</span><span>ความพร้อม</span><span>สิ่งที่ต้องทำต่อ</span></div>
      <div className="divide-y divide-slate-100">{integrations.map((item) => <Link href={item.href} key={item.id} className="grid gap-3 px-5 py-4 transition hover:bg-blue-50/40 lg:grid-cols-[1.35fr_1fr_0.9fr_0.75fr_1.3fr] lg:items-center">
        <div className="flex items-center gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"><FactoryIcon name={item.icon} className="size-5" /></span><div className="min-w-0"><strong className="text-sm text-slate-900">{item.name}</strong><p className="mt-0.5 text-[10px] leading-4 text-slate-400">{item.note}</p></div></div>
        <div><span className="mb-1 block text-[9px] font-black uppercase tracking-wider text-slate-400 lg:hidden">จุดงาน</span><span className="text-xs font-semibold text-slate-600">{item.point}</span></div>
        <div><span className="mb-1 block text-[9px] font-black uppercase tracking-wider text-slate-400 lg:hidden">การเชื่อมต่อ</span><code className="w-fit rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-600">{item.interface}</code><div className="mt-2"><DataStatus state={item.state} /></div></div>
        <div><span className="mb-1 block text-[9px] font-black uppercase tracking-wider text-slate-400 lg:hidden">ความพร้อม</span><ReadinessPill value={item.readiness} /></div>
        <div className="flex items-center gap-2"><span className="flex-1 text-[11px] font-semibold leading-4 text-slate-600">{item.next}</span><FactoryIcon name="chevron" className="size-4 shrink-0 text-blue-600" /></div>
      </Link>)}</div>
    </section>

    <section className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4"><div className="flex items-start gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white text-amber-700 ring-1 ring-amber-200"><FactoryIcon name="incident" className="size-4" /></span><div><h2 className="text-sm font-black text-amber-950">สถานะ “DEMO” ไม่เท่ากับอุปกรณ์ทำงานจริง</h2><p className="mt-1 text-xs leading-5 text-amber-800">ก่อนเปลี่ยนเป็น LIVE ต้องติดตั้งอุปกรณ์ ทำ calibration ส่งข้อมูลด้วย token ของ gateway และผ่านการตรวจค่าเทียบกับเครื่องอ้างอิงโดย QC</p></div></div></section>
  </div>;
}
