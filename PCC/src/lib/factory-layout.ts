/**
 * ผังเครื่องจักรโรงงาน AJ2 สาขาพุนพิน สำหรับฉาก 3D หน้าภาพรวม
 *
 * พิกัดวัดจาก MASTER PLAN AJ2 (QD-R-A192/3, 06-AUG-2025) หน่วยเป็นพิกเซลของผังขนาด 2000 x 1430
 * แกน x ไปทางขวา แกน y ลงล่างตามผัง ความสูง h เป็นค่าประมาณเพื่อให้ดูเป็นสามมิติ ไม่ใช่ขนาดจริง
 * ผังนี้ใช้แสดงตำแหน่งในระบบภายในเท่านั้น
 */

export const PLAN_WIDTH = 2000;
export const PLAN_HEIGHT = 1430;

export type MachineKind =
  | "wet"        // เครื่องจักรสายเปียก (CP, SD, SW, PB, BK, SL)
  | "conveyor"   // สายพาน (CY)
  | "tank"       // ถังกลม (มองจากบนเป็นวงกลม)
  | "dryer"      // เตาอบ
  | "press"      // เครื่องอัด / บรรจุ
  | "scrubber"   // ระบบบำบัดอากาศ
  | "tower"      // หอโรยยาง
  | "pump"       // ปั๊มส่งบ่อสุดท้าย
  | "office"
  | "area";      // พื้นที่บนพื้น (ไม่มีความสูง)

export interface Machine {
  id: string;
  label?: string;
  kind: MachineKind;
  x: number;
  y: number;
  w: number;
  d: number;
  h: number;
  /** ทิศทางสายพาน สำหรับลายเคลื่อนที่ */
  flow?: "left" | "right" | "up" | "down";
}

const box = (id: string, kind: MachineKind, x: number, y: number, w: number, d: number, h: number, label?: string, flow?: Machine["flow"]): Machine =>
  ({ id, kind, x, y, w, d, h, label, flow });

export const MACHINES: Machine[] = [
  // ---- พื้นที่ ----
  box("trolley-area", "area", 925, 210, 482, 192, 2, "Trolley Cleaning Area"),
  box("packing-area", "area", 262, 408, 243, 113, 2, "Packing Area"),

  // ---- ระบบบำบัดอากาศด้านบน ----
  box("ws-1", "scrubber", 395, 128, 70, 52, 46, "Wet Scrubber"),
  box("ws-2", "scrubber", 510, 128, 70, 52, 46, "Wet Scrubber"),
  box("dws-1", "scrubber", 1398, 138, 68, 50, 46, "Dryer Scrubber"),
  box("dws-2", "scrubber", 1488, 138, 68, 50, 46, "Dryer Scrubber"),
  box("duct", "scrubber", 583, 186, 1293, 12, 56),

  // ---- Pre-breaker / Air scrubber 3 สาย (A, B, C) ----
  box("return-top", "conveyor", 112, 205, 783, 22, 14, undefined, "left"),
  box("return-left", "conveyor", 88, 205, 24, 170, 14, undefined, "down"),
  ...(["A", "B", "C"] as const).flatMap((line, index) => {
    const y = 240 + index * 48;
    return [
      box(`pb-${line}1`, "wet", 122, y, 62, 34, 34, `PB ${line}1`),
      box(`pb-${line}2`, "wet", 232, y, 62, 34, 34, `PB ${line}2`),
      box(`as-${line}`, "scrubber", 340, y, 215, 34, 28, "Air Scrubber"),
      box(`cy-${line}`, "conveyor", 557, y + 6, 290 - index * 18, 22, 14, undefined, "right"),
    ];
  }),
  box("cy-down-1", "conveyor", 808, 340, 22, 240, 14, undefined, "down"),
  box("cy-down-2", "conveyor", 843, 250, 20, 590, 14, undefined, "down"),
  box("cy-up", "conveyor", 870, 230, 22, 620, 14, undefined, "up"),

  // ---- Press / Metal detector / Packing ----
  ...[433, 493, 553, 636, 696, 756, 816].map((y, index) => box(`press-${index + 1}`, "press", 737, y, 60, 32, 46, `Press ${index + 1}`)),
  box("u-left", "conveyor", 605, 560, 26, 220, 14, undefined, "up"),
  box("u-right", "conveyor", 707, 555, 26, 150, 14, undefined, "down"),
  box("u-bottom", "conveyor", 605, 778, 128, 24, 14, undefined, "left"),
  box("metal-detector", "press", 590, 493, 62, 36, 30, "Metal Detector"),
  box("packing-line", "conveyor", 363, 423, 270, 20, 14, "Packing Line", "left"),

  box("office", "office", 410, 565, 145, 265, 40, "AJ2 Office"),

  // ---- เตาอบ ----
  box("dryer-a", "dryer", 928, 457, 382, 72, 74, "Dryer A"),
  box("dryer-b", "dryer", 928, 529, 382, 72, 74, "Dryer B"),
  box("dryer-c", "dryer", 928, 650, 382, 72, 74, "Dryer C"),
  box("dryer-d", "dryer", 928, 722, 382, 72, 74, "Dryer D"),
  ...[475, 547, 668, 740].map((y, index) => box(`dryer-in-${index}`, "conveyor", 1312, y, 108, 30, 10, "IN", "left")),
  box("wall", "office", 1455, 410, 12, 525, 60),

  // ---- ฝั่งขวา: รับยางก้อน / ตัด / ถัง ----
  box("sl-91", "wet", 1773, 372, 98, 48, 40, "SL 91"),
  box("cy-91", "conveyor", 1806, 440, 40, 105, 14, undefined, "down"),
  box("t-91", "tank", 1765, 532, 112, 112, 56, "91"),
  box("sl-92-2", "wet", 1615, 548, 97, 72, 40, "SL 92/2"),
  box("bk-92-2", "wet", 1705, 565, 100, 36, 46, "BK 92/2"),
  box("pb-92", "wet", 1793, 655, 64, 36, 34, "PB 92"),
  box("cy-92-2", "conveyor", 1640, 620, 40, 95, 14, undefined, "down"),
  box("cy-92", "conveyor", 1803, 692, 40, 118, 14, undefined, "down"),
  box("cutters", "wet", 1520, 715, 195, 195, 44, "77 · 78 · 76"),
  box("box-92", "wet", 1712, 822, 148, 88, 30, "92"),
  box("bk-14", "wet", 1530, 925, 85, 70, 38, "BK 14"),
  box("bk-13", "wet", 1620, 925, 85, 70, 38, "BK 13"),
  box("t-16", "tank", 1445, 980, 182, 190, 70, "16"),
  box("t-11", "tank", 1615, 908, 186, 186, 70, "11"),
  box("cy-11", "conveyor", 1693, 1075, 36, 138, 14, undefined, "up"),
  box("sl-11", "wet", 1668, 1215, 97, 48, 40, "SL 11"),

  // ---- สายเปียกร่วม ก่อนแยก Line A / B ----
  box("bk-16", "wet", 1360, 1040, 110, 24, 30, "BK 16"),
  box("bk-17", "wet", 1360, 1112, 110, 24, 30, "BK 17"),
  box("pb-16", "wet", 1290, 1033, 70, 40, 36, "PB 16"),
  box("pb-17", "wet", 1290, 1103, 70, 40, 36, "PB 17"),
  box("hopper-17", "wet", 1215, 1030, 72, 116, 44),
  box("t-17", "tank", 1120, 1020, 128, 130, 60, "17"),
  box("sw-21", "wet", 1065, 1050, 80, 26, 30, "SW 21"),
  box("sw-81", "wet", 1065, 1100, 80, 26, 30, "SW 81"),
  box("cp-21", "wet", 998, 1040, 62, 48, 38, "CP 21"),
  box("cp-81", "wet", 998, 1093, 62, 48, 38, "CP 81"),
  box("cy-21", "conveyor", 935, 1048, 63, 30, 14, undefined, "left"),
  box("cy-81", "conveyor", 935, 1101, 63, 30, 14, undefined, "left"),
  box("sd-23", "wet", 877, 1040, 58, 46, 40, "SD 23"),
  box("sd-84", "wet", 877, 1093, 58, 46, 40, "SD 84"),
  box("t-23", "tank", 818, 1008, 84, 84, 44),
  box("t-84", "tank", 818, 1096, 80, 80, 44),

  // ---- Line A (ไปบ่อสุดท้าย Line A) ----
  box("bk-24", "wet", 768, 1035, 60, 34, 34, "BK 24"),
  box("cp-24", "wet", 704, 1028, 64, 48, 38, "CP 24"),
  box("cy-24-26", "conveyor", 640, 1036, 64, 32, 14, undefined, "left"),
  box("cp-26", "wet", 578, 1028, 62, 48, 38, "CP 26"),
  box("cy-26-27", "conveyor", 515, 1036, 63, 32, 14, undefined, "left"),
  box("cp-27", "wet", 453, 1028, 62, 48, 38, "CP 27"),
  box("cy-27-28", "conveyor", 388, 1036, 65, 32, 14, undefined, "left"),
  box("sd-28", "wet", 326, 1028, 62, 48, 40, "SD 28"),
  box("pump-a", "pump", 214, 1026, 60, 56, 30, "บ่อสุดท้าย A"),

  // ---- Line B ----
  box("bk-85", "wet", 845, 1160, 24, 62, 34, "BK 85"),
  box("cp-85", "wet", 827, 1213, 60, 48, 38, "CP 85"),
  box("cy-85-87", "conveyor", 730, 1221, 97, 32, 14, undefined, "left"),
  box("cp-87", "wet", 668, 1213, 62, 48, 38, "CP 87"),
  box("cy-87-88", "conveyor", 562, 1221, 106, 32, 14, undefined, "left"),
  box("cp-88", "wet", 500, 1213, 62, 48, 38, "CP 88"),
  box("cy-88-89", "conveyor", 385, 1221, 115, 32, 14, undefined, "left"),
  box("sd-89", "wet", 325, 1213, 60, 48, 40, "SD 89"),
  box("pump-b", "pump", 214, 1211, 60, 56, 30, "บ่อสุดท้าย B"),

  // ---- หอโรยยาง ----
  box("tower-1", "tower", 1083, 903, 108, 74, 96, "หอโรยยาง"),
  box("tower-2", "tower", 1203, 903, 108, 74, 96, "หอโรยยาง"),
];

/** เส้นทางวัตถุดิบบนพื้น (แสดงเป็นเส้นวิ่ง) */
export interface FlowPath {
  id: string;
  kind: "pipe" | "trolley" | "product";
  points: Array<[number, number]>;
}

export const FLOWS: FlowPath[] = [
  // ปั๊มบ่อสุดท้าย → ท่อส่งขึ้นหอโรยยาง (เส้นประในผัง)
  { id: "pipe-a", kind: "pipe", points: [[244, 1026], [244, 882], [1137, 882], [1137, 903]] },
  { id: "pipe-b", kind: "pipe", points: [[230, 1211], [230, 860], [1257, 860], [1257, 903]] },
  // หอโรยยาง → เก๊ะเข้าเตา (ผ่านกล้องนับเก๊ะ)
  { id: "trolley", kind: "trolley", points: [[1257, 903], [1440, 860], [1440, 490], [1420, 490]] },
  // เตา → Pre-breaker → Press → บรรจุ
  { id: "product", kind: "product", points: [[928, 493], [900, 300], [881, 222], [100, 216], [100, 360], [153, 360]] },
];

export type StationKey = "final-pond" | "rack-infeed" | "furnace-temperature" | "rubber-scale" | "rubber-odor";

/** จุดตรวจของ PCC บนผัง — ตำแหน่งที่ป้ายข้อมูลลอยอยู่ */
export const STATION_SPOTS: Record<StationKey, { x: number; y: number; z: number; title: string; place: string }> = {
  "final-pond": { x: 244, y: 1054, z: 70, title: "บ่อสุดท้าย Line A", place: "ปั๊มส่งบ่อสุดท้าย หลัง SD 28" },
  "rack-infeed": { x: 1250, y: 940, z: 150, title: "นับเก๊ะหอโรยยาง", place: "หอโรยยาง ก่อนเข้าเตา Dryer A–D" },
  "furnace-temperature": { x: 1118, y: 625, z: 130, title: "อุณหภูมิเตา", place: "Dryer A–D" },
  "rubber-scale": { x: 767, y: 640, z: 100, title: "ตาชั่งน้ำหนักยาง", place: "สาย Press 1–7" },
  "rubber-odor": { x: 488, y: 154, z: 100, title: "กลิ่นยาง (H₂S)", place: "ยังไม่ติดตั้งเซ็นเซอร์" },
};
