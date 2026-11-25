/**
 * "rack-infeed" คือจุดนับเก๊ะที่ออกจากหอโรยยางก่อนเข้าเตา (เดิมใช้ชื่อ "checker-infeed")
 * ชื่อเดิมสื่อว่าเป็นการนับก้อนยาง ซึ่งเป็นคนละจุดกับที่กล้องตัวนี้มองอยู่จริง
 * และชื่อชุด rubber_* ถูกกันไว้ให้เซ็นเซอร์นับก้อนยางก่อนแพ็คที่จะเพิ่มเข้ามาภายหลัง
 */
export type StationId = "final-pond" | "rack-infeed" | "rubber-odor" | "rubber-scale" | "furnace-temperature";

export interface StationDefinition {
  id: StationId;
  name: string;
  shortName: string;
  description: string;
  icon: "pond" | "conveyor" | "odor" | "scale" | "thermometer";
}

export const STATIONS: StationDefinition[] = [
  {
    id: "final-pond",
    name: "บ่อสุดท้าย",
    shortName: "บ่อสุดท้าย",
    description: "ติดตามอุณหภูมิ ค่า pH และผลประเมินจากระบบ AI",
    icon: "pond",
  },
  {
    id: "rack-infeed",
    name: "หอโรยยาง · นับเก๊ะเข้าเตา",
    shortName: "นับเก๊ะเข้าเตา",
    description: "จำนวนเก๊ะรายกะ รายชั่วโมง และสถานะการนับของกล้อง",
    icon: "conveyor",
  },
  {
    id: "rubber-odor",
    name: "กลิ่นยาง",
    shortName: "กลิ่นยาง",
    description: "ค่า H₂S แบบเรียลไทม์จากเซ็นเซอร์ตรวจกลิ่นในกระบวนการ",
    icon: "odor",
  },
  {
    id: "rubber-scale",
    name: "ตาชั่งน้ำหนักยาง",
    shortName: "ตาชั่งน้ำหนัก",
    description: "น้ำหนักล่าสุด เป้าหมาย ค่าคลาดเคลื่อน และล็อตผลิต",
    icon: "scale",
  },
  {
    id: "furnace-temperature",
    name: "อุณหภูมิเตา",
    shortName: "อุณหภูมิเตา",
    description: "เปรียบเทียบ Digital Thermometer, Burner และ Recorder",
    icon: "thermometer",
  },
];

export const STATION_BY_ID = Object.fromEntries(
  STATIONS.map((station) => [station.id, station]),
) as Record<StationId, StationDefinition>;

export function isStationId(value: string): value is StationId {
  return value in STATION_BY_ID;
}

