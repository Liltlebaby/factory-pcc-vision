"use client";

import { useId } from "react";

interface Band {
  value: number;
  color: string;
  dashed?: boolean;
}

interface Props {
  values: number[];
  min: number;
  max: number;
  color: string;
  bands?: Band[];
  height?: number;
  /** วาดพื้นไล่เฉดใต้เส้นกราฟ */
  area?: boolean;
}

/** กราฟเส้นแบบเบา ๆ วาดด้วย SVG เอง เพื่อไม่ต้องเพิ่ม dependency ในช่วง Prototype */
export function Sparkline({
  values,
  min,
  max,
  color,
  bands = [],
  height = 64,
  area = true,
}: Props) {
  const gradientId = useId();
  const width = 300;
  const span = max - min || 1;
  const toY = (v: number) =>
    height - ((Math.min(Math.max(v, min), max) - min) / span) * height;
  // เผื่อขอบไว้ให้จุดค่าล่าสุดไม่ถูกตัด
  const padX = 4;
  const toX = (i: number) =>
    values.length > 1
      ? padX + (i / (values.length - 1)) * (width - padX * 2)
      : padX;

  const line =
    values.length > 1
      ? values.map((v, i) => `${toX(i)},${toY(v)}`).join(" ")
      : "";

  // ไม่มีข้อมูลแล้ววาดแต่เส้นเกณฑ์ลอย ๆ ทำให้ดูเหมือนกราฟเสีย
  // จึงบอกตรง ๆ ว่ายังไม่มีข้อมูล แทนที่จะปล่อยกรอบว่าง
  if (values.length === 0) {
    // เขียนข้อความเป็น HTML ไม่ใช่ <text> ใน SVG เพราะ viewBox ถูกยืดเต็มความกว้าง
    // ตัวอักษรในนั้นจะถูกขยายตามไปด้วยจนใหญ่ผิดสัดส่วน
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/60 text-xs text-slate-400"
        style={{ height }}
        role="img"
        aria-label="ยังไม่มีข้อมูลย้อนหลังสำหรับกราฟนี้"
      >
        ยังไม่มีข้อมูลย้อนหลัง
      </div>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label="กราฟค่าย้อนหลัง"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.28} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>

      {bands.map((band) => (
        <line
          key={`${band.value}-${band.color}`}
          x1={0}
          x2={width}
          y1={toY(band.value)}
          y2={toY(band.value)}
          stroke={band.color}
          strokeWidth={1}
          strokeDasharray={band.dashed ? "5 5" : undefined}
          opacity={band.dashed ? 0.7 : 0.55}
        />
      ))}

      {line && area && (
        <polygon
          points={`${padX},${height} ${line} ${width - padX},${height}`}
          fill={`url(#${gradientId})`}
        />
      )}

      {line && (
        <polyline
          points={line}
          fill="none"
          stroke={color}
          strokeWidth={2.25}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {values.length > 0 && (
        <circle
          cx={toX(values.length - 1)}
          cy={toY(values[values.length - 1])}
          r={3.25}
          fill="#ffffff"
          stroke={color}
          strokeWidth={2.25}
        />
      )}
    </svg>
  );
}
