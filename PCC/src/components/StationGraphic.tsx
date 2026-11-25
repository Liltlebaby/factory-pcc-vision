"use client";

/**
 * ภาพประกอบจุดงานบนหน้าภาพรวม
 *
 * ของเดิมวาดด้วย <div> ซ้อนกรอบสี่เหลี่ยม ทำให้ดูเหมือนกล่องเปล่ามากกว่าอุปกรณ์จริง
 * และย่อ/ขยายตามความกว้างการ์ดไม่ได้ ชุดนี้วาดด้วย SVG ที่มี viewBox คงที่
 * จึงคมทุกความละเอียดและปรับสีตามสถานะจริงของจุดงานได้
 *
 * ทุกภาพรับค่าที่วัดได้เข้ามา เพื่อให้ภาพกับตัวเลขบนการ์ดเป็นเรื่องเดียวกัน
 * ไม่ใช่ภาพตกแต่งที่นิ่งอยู่กับที่
 */

export type Tone = "ok" | "warn" | "alert" | "idle";

/** แปลงสถานะจุดงานเป็นโทนสีของภาพ เพื่อให้ภาพกับป้ายสถานะไม่ขัดกัน */
export function toneOf(status: "GREEN" | "YELLOW" | "RED" | "SENSOR_ERROR"): Tone {
  if (status === "RED") return "alert";
  if (status === "YELLOW") return "warn";
  if (status === "GREEN") return "ok";
  return "idle";
}

const TONE: Record<Tone, { line: string; fill: string; soft: string }> = {
  ok: { line: "#0284c7", fill: "#0ea5e9", soft: "#e0f2fe" },
  warn: { line: "#d97706", fill: "#f59e0b", soft: "#fef3c7" },
  alert: { line: "#dc2626", fill: "#ef4444", soft: "#fee2e2" },
  idle: { line: "#94a3b8", fill: "#cbd5e1", soft: "#f1f5f9" },
};

/* ───────────────────────── บ่อสุดท้าย ───────────────────────── */

export function PondGraphic({
  temp,
  ph,
  tone = "ok",
}: {
  temp?: number;
  ph?: number;
  tone?: Tone;
}) {
  const c = TONE[tone];
  const label = [
    "ภาพตัดขวางบ่อสุดท้าย มีหัววัดอุณหภูมิและหัววัดค่า pH จุ่มอยู่ในน้ำ",
    typeof temp === "number" ? `อุณหภูมิน้ำ ${temp.toFixed(1)} องศาเซลเซียส` : null,
    typeof ph === "number" ? `ค่า pH ${ph.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <svg viewBox="0 0 240 140" className="h-full w-full" role="img" aria-label={label}>
      <defs>
        <linearGradient id="pondWater" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="100%" stopColor="#0369a1" />
        </linearGradient>
        <clipPath id="pondInner">
          <rect x="24" y="40" width="192" height="80" rx="9" />
        </clipPath>
      </defs>

      {/* ท่อน้ำเข้าและท่อล้นออก — บ่อสุดท้ายเป็นบ่อไหลผ่าน ไม่ใช่ถังปิด */}
      <path d="M0 58h26M216 98h24" stroke="#94a3b8" strokeWidth="7" strokeLinecap="round" />

      {/* ตัวบ่อ */}
      <rect x="24" y="40" width="192" height="80" rx="9" fill="#f8fafc" stroke="#cbd5e1" strokeWidth="3" />

      <g clipPath="url(#pondInner)">
        <rect x="24" y="62" width="192" height="58" fill="url(#pondWater)" opacity="0.92" />
        {/* ผิวน้ำ — ขยับช้า ๆ ให้รู้ว่าระบบยังเดินอยู่ */}
        <path
          className="pond-wave"
          d="M-20 62q24-6 48 0t48 0 48 0 48 0 48 0v16H-20z"
          fill="#bae6fd"
          opacity="0.9"
        />
        {/* น้ำที่ไหลเข้ากระทบผิวบ่อ */}
        <circle cx="34" cy="66" r="6" fill="#ffffff" opacity="0.35" />
        <circle cx="72" cy="96" r="3" fill="#ffffff" opacity="0.4" />
        <circle cx="106" cy="108" r="2" fill="#ffffff" opacity="0.35" />
        <circle cx="180" cy="100" r="2.5" fill="#ffffff" opacity="0.35" />
      </g>

      {/* คานยึดหัววัดพาดปากบ่อ */}
      <rect x="58" y="22" width="126" height="9" rx="4.5" fill="#e2e8f0" stroke="#cbd5e1" strokeWidth="2" />

      {/* หัววัดอุณหภูมิ */}
      <line x1="92" y1="31" x2="92" y2="90" stroke="#64748b" strokeWidth="4" strokeLinecap="round" />
      <circle cx="92" cy="95" r="8.5" fill={c.fill} stroke="#ffffff" strokeWidth="2.5" />
      <text x="92" y="98.5" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#ffffff">
        °C
      </text>

      {/* หัววัด pH */}
      <line x1="150" y1="31" x2="150" y2="80" stroke="#64748b" strokeWidth="4" strokeLinecap="round" />
      <circle cx="150" cy="85" r="8.5" fill="#7c3aed" stroke="#ffffff" strokeWidth="2.5" />
      <text x="150" y="88.5" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#ffffff">
        pH
      </text>

      {/* ฐานบ่อ */}
      <path d="M18 122h204M44 122v9M196 122v9" stroke="#cbd5e1" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

/* ──────────── หอโรยยาง · นับเก๊ะก่อนเข้าเตา ──────────── */

/**
 * จุดนี้กล้องนับ "เก๊ะ" ที่ออกจากหอโรยยางแล้ววิ่งเข้าเตา ไม่ใช่ก้อนยางบนสายพาน
 * ภาพจึงเล่าเป็นลำดับซ้ายไปขวา: หอโรยยาง → เก๊ะบนราง → ปากเตา
 * โดยมีกล้องแขวนอยู่เหนือเส้นนับตรงกลาง ตรงกับที่ Camera 09 ติดตั้งจริง
 */
export function RackInfeedGraphic({
  live = false,
  blind = false,
  tracking,
}: {
  live?: boolean;
  /** DVR บอกว่าช่องนี้ไม่มีสัญญาณเข้า — กล้องยังส่งเฟรมแต่เป็นภาพ NO VIDEO */
  blind?: boolean;
  tracking?: number;
}) {
  const c = blind ? TONE.alert : live ? TONE.ok : TONE.idle;
  const label = blind
    ? "กล้องนับเก๊ะไม่มีสัญญาณภาพเข้าเครื่องบันทึก"
    : live
      ? "เก๊ะออกจากหอโรยยางวิ่งบนรางเข้าเตา มีกล้องนับอยู่เหนือเส้นนับ"
      : "เก๊ะออกจากหอโรยยางวิ่งบนรางเข้าเตา กล้องนับยังไม่ส่งข้อมูล";

  return (
    <svg viewBox="0 0 240 140" className="h-full w-full" role="img" aria-label={label}>
      <defs>
        <linearGradient id="visionCone" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c.fill} stopOpacity="0.30" />
          <stop offset="100%" stopColor={c.fill} stopOpacity="0.03" />
        </linearGradient>
      </defs>

      {/* หอโรยยาง พร้อมรางโรยลงเก๊ะ */}
      <rect x="4" y="6" width="34" height="98" rx="6" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="2.5" />
      <path d="M11 24h20M11 38h20M11 52h20" stroke="#cbd5e1" strokeWidth="3" strokeLinecap="round" />
      <path d="M38 48l20 18v9l-20-14z" fill="#cbd5e1" stroke="#94a3b8" strokeWidth="2.5" strokeLinejoin="round" />

      {/* เตาอบ — เก๊ะวิ่งเข้าทางปากเตาด้านซ้าย */}
      <path d="M200 40c4-5 4-9 0-14M214 40c4-5 4-9 0-14M228 40c4-5 4-9 0-14" stroke="#f59e0b" strokeWidth="2.5" strokeLinecap="round" opacity="0.75" />
      <rect x="192" y="46" width="48" height="66" rx="6" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="2.5" />
      <rect x="186" y="58" width="26" height="46" rx="4" fill="#1e293b" />

      {/* กล้องและกรวยภาพ */}
      <path d="M127 0v10" stroke="#94a3b8" strokeWidth="4" strokeLinecap="round" />
      {!blind && <path d="M113 36h28l50 68H63z" fill="url(#visionCone)" />}
      <rect x="104" y="10" width="46" height="26" rx="7" fill="#1e3a8a" />
      <circle cx="127" cy="23" r="8" fill="#bfdbfe" />
      <circle cx="127" cy="23" r="3.5" fill="#1e3a8a" />
      <circle cx="143" cy="16" r="2.5" fill={blind ? "#ef4444" : live ? "#4ade80" : "#94a3b8"} />

      {/* เส้นนับ — เก๊ะถูกนับเมื่อกึ่งกลางกรอบข้ามเส้นนี้ */}
      <line x1="127" y1="40" x2="127" y2="118" stroke={c.line} strokeWidth="2.5" strokeDasharray="6 5" strokeLinecap="round" />

      {/* ราง */}
      <rect x="28" y="104" width="170" height="12" rx="6" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="2.5" />
      <path className="belt-move" d="M38 110h150" stroke="#94a3b8" strokeWidth="2.5" strokeDasharray="7 11" strokeLinecap="round" />

      {/* เก๊ะบนราง — ใบขวาสุดกำลังเข้าปากเตา */}
      <Rack x={50} />
      <Rack x={106} highlighted={!blind} tone={c} tracking={tracking} />
      <Rack x={158} />

      {/* ขาตั้งราง */}
      <path d="M46 117v13M180 117v13M34 130h156" stroke="#cbd5e1" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

/** เก๊ะ: โครงเหล็กสองชั้นมีล้อ วางยางที่โรยแล้วไว้บนชั้น */
function Rack({
  x,
  highlighted = false,
  tone,
  tracking,
}: {
  x: number;
  highlighted?: boolean;
  tone?: { line: string; fill: string; soft: string };
  tracking?: number;
}) {
  const top = 72;
  return (
    <g>
      <rect x={x} y={top} width="42" height="32" rx="4" fill="#f8fafc" stroke="#475569" strokeWidth="2.5" />
      <rect x={x + 5} y={top + 5} width="32" height="7" rx="2.5" fill="#64748b" />
      <rect x={x + 5} y={top + 19} width="32" height="7" rx="2.5" fill="#64748b" />
      <path d={`M${x} ${top + 16}h42`} stroke="#94a3b8" strokeWidth="2" />
      <circle cx={x + 10} cy={top + 36} r="3.5" fill="#64748b" />
      <circle cx={x + 32} cy={top + 36} r="3.5" fill="#64748b" />
      {highlighted && tone && (
        <>
          <rect
            x={x - 5}
            y={top - 5}
            width="52"
            height="46"
            rx="5"
            fill="none"
            stroke={tone.line}
            strokeWidth="2.5"
          />
          <rect x={x - 5} y={top - 21} width={tracking === undefined ? 26 : 34} height="16" rx="4" fill={tone.line} />
          <text
            x={x - 5 + (tracking === undefined ? 13 : 17)}
            y={top - 9.5}
            textAnchor="middle"
            fontSize="9.5"
            fontWeight="700"
            fill="#ffffff"
          >
            {tracking === undefined ? "AI" : `×${tracking}`}
          </text>
        </>
      )}
    </g>
  );
}

/* ───────────────────────── เตาอบ ───────────────────────── */

export function FurnaceGraphic({
  value,
  tone = "ok",
}: {
  value?: number;
  tone?: Tone;
}) {
  const c = TONE[tone];
  const reading = typeof value === "number" ? value.toFixed(1) : "---.-";

  return (
    <svg
      viewBox="0 0 200 120"
      className="h-full w-full"
      role="img"
      aria-label={`เตาอบพร้อมหัววัดอุณหภูมิ อ่านได้ ${reading} องศาเซลเซียส`}
    >
      <defs>
        <linearGradient id="ovenGlow" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.85" />
          <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.15" />
        </linearGradient>
      </defs>

      {/* ไอความร้อนเหนือเตา */}
      <path
        d="M62 18c4-5 4-9 0-13M82 18c4-5 4-9 0-13M102 18c4-5 4-9 0-13"
        stroke="#f59e0b"
        strokeWidth="2.5"
        strokeLinecap="round"
        opacity="0.75"
      />

      {/* ตัวเตาและช่องมองไฟ */}
      <rect x="24" y="24" width="124" height="74" rx="8" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="2.5" />
      <rect x="36" y="36" width="76" height="50" rx="5" fill="#1e293b" />
      <rect x="42" y="58" width="64" height="22" rx="4" fill="url(#ovenGlow)" />
      <rect x="118" y="50" width="9" height="22" rx="4.5" fill="#94a3b8" />

      {/* หัววัดอุณหภูมิที่เสียบเข้าไปในเตา */}
      <line x1="148" y1="44" x2="172" y2="44" stroke="#64748b" strokeWidth="4" strokeLinecap="round" />
      <circle cx="180" cy="44" r="8.5" fill={c.fill} stroke="#ffffff" strokeWidth="2.5" />
      <text x="180" y="47.5" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#ffffff">
        °C
      </text>

      {/* จอแสดงค่าที่อ่านได้ */}
      <rect x="150" y="62" width="46" height="21" rx="5" fill="#0f172a" />
      <text
        x="173"
        y="77"
        textAnchor="middle"
        fontSize="12.5"
        fontWeight="700"
        fill={c.fill}
        fontFamily="var(--font-mono, monospace)"
      >
        {reading}
      </text>

      {/* ขาตั้ง */}
      <path d="M40 98v10M132 98v10M28 108h116" stroke="#cbd5e1" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

/* ───────────────────── ตาชั่งน้ำหนักยาง ───────────────────── */

export function ScaleGraphic({
  value,
  tone = "ok",
}: {
  value?: number;
  tone?: Tone;
}) {
  const c = TONE[tone];
  const reading = typeof value === "number" ? value.toFixed(2) : "--.--";

  return (
    <svg
      viewBox="0 0 200 116"
      className="h-full w-full"
      role="img"
      aria-label={`ตาชั่งตั้งพื้นพร้อมก้อนยางวางบนแท่นชั่ง น้ำหนัก ${reading} กิโลกรัม`}
    >
      {/* ก้อนยางบนแท่น */}
      <rect x="66" y="16" width="68" height="34" rx="10" fill="#475569" />
      <rect x="74" y="23" width="52" height="8" rx="4" fill="#94a3b8" opacity="0.45" />
      <rect x="74" y="36" width="34" height="6" rx="3" fill="#94a3b8" opacity="0.3" />
      <ellipse cx="100" cy="52" rx="36" ry="3" fill="#0f172a" opacity="0.12" />

      {/* แท่นชั่ง */}
      <rect x="40" y="52" width="120" height="13" rx="6.5" fill="#f1f5f9" stroke="#94a3b8" strokeWidth="2.5" />

      {/* ตัวเครื่องชั่ง */}
      <path d="M52 65h96l10 34H42z" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="2.5" strokeLinejoin="round" />

      {/* หน้าจอแสดงน้ำหนัก */}
      <rect x="66" y="72" width="68" height="21" rx="5" fill="#0f172a" />
      <text
        x="100"
        y="87"
        textAnchor="middle"
        fontSize="14"
        fontWeight="700"
        fill={c.fill}
        fontFamily="var(--font-mono, monospace)"
      >
        {reading}
      </text>

      {/* ไฟสถานะและขาตั้ง */}
      <circle cx="146" cy="82" r="3.5" fill={c.fill} />
      <path d="M36 99h128" stroke="#cbd5e1" strokeWidth="5" strokeLinecap="round" />
      <path d="M56 104v6M144 104v6" stroke="#cbd5e1" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
