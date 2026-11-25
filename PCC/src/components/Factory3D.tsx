"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";
import { FLOWS, MACHINES, PLAN_HEIGHT, PLAN_WIDTH, STATION_SPOTS, type Machine, type StationKey } from "@/lib/factory-layout";
import type { DataState } from "./StatusMark";
import styles from "./Factory3D.module.css";

/** ย่อพิกัดผัง (2000 px) ให้เหลือพื้นฉาก 1000 px */
const S = 0.5;
const FLOOR_W = PLAN_WIDTH * S;
const FLOOR_H = PLAN_HEIGHT * S;

export type SpotTone = "ok" | "warn" | "alert" | "idle";

export interface FactorySpot {
  key: StationKey;
  value: string;
  unit?: string;
  detail: string;
  tone: SpotTone;
  dataState: DataState;
}

const STATE_LABEL: Record<DataState, string> = {
  LIVE: "สด",
  STALE: "ข้อมูลเก่า",
  OFFLINE: "ขาดการเชื่อมต่อ",
  NOT_INSTALLED: "ยังไม่ติดตั้ง",
  DEMO: "ข้อมูลจำลอง",
};

/** เครื่องที่ผูกกับจุดตรวจ ให้เรืองแสงตามสถานะของจุดนั้น */
const STATION_MACHINES: Record<StationKey, string[]> = {
  "final-pond": ["pump-a"],
  "rack-infeed": ["tower-1", "tower-2"],
  "furnace-temperature": ["dryer-a", "dryer-b", "dryer-c", "dryer-d"],
  "rubber-scale": ["press-1", "press-2", "press-3", "press-4", "press-5", "press-6", "press-7"],
  "rubber-odor": ["ws-1", "ws-2"],
};

interface View { spin: number; tilt: number; zoom: number }
const DEFAULT_VIEW: View = { spin: -24, tilt: 56, zoom: 1 };
const TOP_VIEW: View = { spin: 0, tilt: 0, zoom: 1 };
const ZOOM_MIN = 0.6;
const ZOOM_MAX = 2.6;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

function Box({ machine, tone }: { machine: Machine; tone?: SpotTone }) {
  const w = machine.w * S;
  const d = machine.d * S;
  const h = machine.h * S;
  const style = { left: machine.x * S, top: machine.y * S, width: w, height: d, "--h": `${h}px`, "--w": `${w}px`, "--d": `${d}px` } as CSSProperties;
  const className = [styles.box, styles[machine.kind], tone ? styles[`tone-${tone}`] : "", machine.flow ? styles[`flow-${machine.flow}`] : ""].join(" ");

  if (machine.kind === "area") {
    return <div className={className} style={style}>{machine.label ? <span className={styles.areaLabel}>{machine.label}</span> : null}</div>;
  }

  if (machine.kind === "tank") {
    const r = Math.min(w, d) / 2;
    const segments = 10;
    const segment = (2 * Math.PI * r) / segments + 0.8;
    return <div className={className} style={style}>
      <div className={styles.tankBase} />
      {Array.from({ length: segments }, (_, index) => <i key={index} className={styles.tankWall} style={{ width: segment, height: h, marginLeft: -segment / 2, transform: `rotateZ(${(index * 360) / segments}deg) translateY(${r - 0.5}px) rotateX(90deg)` }} />)}
      <div className={styles.tankTop}>{machine.label ? <span>{machine.label}</span> : null}</div>
    </div>;
  }

  return <div className={className} style={style}>
    <i className={`${styles.face} ${styles.back}`} />
    <i className={`${styles.face} ${styles.left}`} />
    <i className={`${styles.face} ${styles.right}`} />
    <i className={`${styles.face} ${styles.front}`} />
    <div className={`${styles.face} ${styles.top}`}>{machine.label && w >= 26 ? <span>{machine.label}</span> : null}</div>
  </div>;
}

function flowPath(points: Array<[number, number]>) {
  return points.map(([x, y], index) => `${index ? "L" : "M"}${(x * S).toFixed(1)} ${(y * S).toFixed(1)}`).join(" ");
}

export function Factory3D({ spots }: { spots: FactorySpot[] }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const view = useRef<View>({ ...DEFAULT_VIEW });
  const target = useRef<View | null>(null);
  const velocity = useRef(0);
  const dirty = useRef(true);
  const drag = useRef<{ startX: number; startY: number; x: number; y: number; id: number; dragging: boolean } | null>(null);
  const suppressClick = useRef(false);
  const autoSpinRef = useRef(false);
  const [autoSpin, setAutoSpin] = useState(false);
  const [mode, setMode] = useState<"3d" | "top">("3d");

  const toneByStation = new Map(spots.map((spot) => [spot.key, spot.tone]));
  const machineTone = new Map<string, SpotTone>();
  for (const [key, ids] of Object.entries(STATION_MACHINES) as Array<[StationKey, string[]]>) {
    const tone = toneByStation.get(key);
    if (tone) ids.forEach((id) => machineTone.set(id, tone));
  }

  useEffect(() => {
    autoSpinRef.current = autoSpin;
  }, [autoSpin]);

  // มุมกล้องไม่ผ่าน React และไม่ตั้ง CSS variable ที่กล่องแม่ ไม่งั้นหน้าของเครื่องจักรราว 800 ชิ้น
  // ต้องคำนวณ style ใหม่ทุกเฟรมจนกระตุก จึงเขียน transform ให้ฉากตรง ๆ และส่งตัวแปรให้เฉพาะป้าย 5 อัน
  useEffect(() => {
    const element = viewportRef.current;
    const stage = stageRef.current;
    if (!element || !stage) return;
    let fit = 0.8;
    const apply = () => {
      const { spin, tilt, zoom } = view.current;
      stage.style.transform = `translate(-50%, -50%) rotateX(${tilt}deg) rotateZ(${spin}deg) scale(${fit * zoom})`;
      stage.querySelectorAll<HTMLElement>("[data-spot]").forEach((spot) => {
        spot.style.setProperty("--spin", `${spin}deg`);
        spot.style.setProperty("--tilt", `${tilt}deg`);
        spot.style.setProperty("--fit", String(fit));
      });
    };
    const resize = () => {
      fit = clamp(element.clientWidth / (FLOOR_W * 1.18), 0.32, 1.25);
      dirty.current = true;
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    const tick = () => {
      const current = view.current;
      const goal = target.current;
      if (goal) {
        const step = reduced.matches ? 1 : 0.16;
        current.spin += (goal.spin - current.spin) * step;
        current.tilt += (goal.tilt - current.tilt) * step;
        current.zoom += (goal.zoom - current.zoom) * step;
        if (Math.abs(goal.spin - current.spin) < 0.05 && Math.abs(goal.tilt - current.tilt) < 0.05 && Math.abs(goal.zoom - current.zoom) < 0.002) {
          view.current = { ...goal };
          target.current = null;
        }
        dirty.current = true;
      } else if (!drag.current?.dragging && Math.abs(velocity.current) > 0.02) {
        // ปล่อยเมาส์แล้วไหลต่ออีกนิด ให้รู้สึกลื่น
        current.spin += velocity.current;
        velocity.current *= 0.92;
        dirty.current = true;
      } else if (autoSpinRef.current && !drag.current && !reduced.matches) {
        current.spin -= 0.12;
        dirty.current = true;
      }
      if (dirty.current) {
        dirty.current = false;
        apply();
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const base = target.current ?? view.current;
      target.current = { ...base, zoom: clamp(base.zoom * Math.exp(-event.deltaY * 0.0015), ZOOM_MIN, ZOOM_MAX) };
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      element.removeEventListener("wheel", onWheel);
    };
  }, []);

  const goTo = (next: View, nextMode: "3d" | "top") => {
    velocity.current = 0;
    target.current = { ...next, spin: next.spin + Math.round((view.current.spin - next.spin) / 360) * 360 };
    setMode(nextMode);
  };
  const rotateBy = (degrees: number) => {
    velocity.current = 0;
    const base = target.current ?? view.current;
    target.current = { ...base, spin: base.spin + degrees };
  };
  const zoomBy = (factor: number) => {
    const base = target.current ?? view.current;
    target.current = { ...base, zoom: clamp(base.zoom * factor, ZOOM_MIN, ZOOM_MAX) };
  };

  // ลากได้ทุกที่รวมถึงบนป้าย ขยับเกิน 5 px จึงนับเป็นการหมุน ไม่งั้นถือเป็นการกดป้ายตามปกติ
  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest("button")) return;
    drag.current = { startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, id: event.pointerId, dragging: false };
    velocity.current = 0;
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    if (!current.dragging) {
      if (Math.hypot(event.clientX - current.startX, event.clientY - current.startY) < 5) return;
      current.dragging = true;
      target.current = null;
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    const dx = event.clientX - current.x;
    const dy = event.clientY - current.y;
    current.x = event.clientX;
    current.y = event.clientY;
    // ฉากเอียงเข้าหาจอ ขอบด้านหน้าต้องเลื่อนตามมือ จึงหมุนสวนทิศ rotateZ
    view.current.spin -= dx * 0.4;
    view.current.tilt = clamp(view.current.tilt - dy * 0.3, 0, 75);
    velocity.current = -dx * 0.4;
    dirty.current = true;
  };
  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    if (current.dragging) {
      suppressClick.current = true;
      if (mode === "top" && view.current.tilt > 4) setMode("3d");
    }
    drag.current = null;
  };
  const onClickCapture = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!suppressClick.current) return;
    suppressClick.current = false;
    event.preventDefault();
    event.stopPropagation();
  };

  return <section aria-labelledby="factory-3d-title" className={styles.shell}>
    <header className={styles.header}>
      <div>
        <p className={styles.kicker}><span className={styles.liveDot} />Digital twin · AJ2 Phunphin</p>
        <h2 id="factory-3d-title" className={styles.title}>ผังโรงงาน 3 มิติ</h2>
        <p className={styles.subtitle}>ลากซ้าย–ขวาเพื่อหมุน · ลากขึ้น–ลงเพื่อเอียง · ดับเบิลคลิกกลับมุมเดิม</p>
      </div>
      <div className={styles.controls} role="toolbar" aria-label="มุมมองผัง 3 มิติ">
        <button type="button" aria-label="หมุนซ้าย 45 องศา" title="หมุนซ้าย" onClick={() => rotateBy(-45)}>⟲</button>
        <button type="button" aria-label="หมุนขวา 45 องศา" title="หมุนขวา" onClick={() => rotateBy(45)}>⟳</button>
        <button type="button" className={mode === "3d" ? styles.active : ""} onClick={() => goTo(DEFAULT_VIEW, "3d")}>3D</button>
        <button type="button" className={mode === "top" ? styles.active : ""} onClick={() => goTo(TOP_VIEW, "top")}>มุมบน</button>
        <button type="button" aria-pressed={autoSpin} className={autoSpin ? styles.active : ""} onClick={() => setAutoSpin((value) => !value)}>หมุนอัตโนมัติ</button>
        <button type="button" aria-label="ซูมเข้า" onClick={() => zoomBy(1.25)}>+</button>
        <button type="button" aria-label="ซูมออก" onClick={() => zoomBy(1 / 1.25)}>−</button>
      </div>
    </header>

    <div
      ref={viewportRef}
      className={styles.viewport}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onClickCapture={onClickCapture}
      onDoubleClick={() => goTo(DEFAULT_VIEW, "3d")}
      onDragStart={(event) => event.preventDefault()}
    >
      <div ref={stageRef} className={styles.stage} style={{ width: FLOOR_W, height: FLOOR_H }}>
        <div className={styles.floor} />
        <svg className={styles.flows} width={FLOOR_W} height={FLOOR_H} viewBox={`0 0 ${FLOOR_W} ${FLOOR_H}`} aria-hidden="true">
          {FLOWS.map((flow) => <path key={flow.id} d={flowPath(flow.points)} className={styles[`path-${flow.kind}`]} />)}
        </svg>
        {FLOWS.flatMap((flow) => {
          const count = flow.kind === "trolley" ? 3 : 2;
          return Array.from({ length: count }, (_, index) => <i
            key={`${flow.id}-${index}`}
            className={`${styles.mover} ${styles[`mover-${flow.kind}`]}`}
            style={{ offsetPath: `path("${flowPath(flow.points)}")`, animationDelay: `${(index * -6.6) / count}s` }}
          />);
        })}

        {MACHINES.map((machine) => <Box key={machine.id} machine={machine} tone={machineTone.get(machine.id)} />)}

        {spots.map((spot) => {
          const place = STATION_SPOTS[spot.key];
          return <div key={spot.key} data-spot className={`${styles.spot} ${styles[`tone-${spot.tone}`]}`} style={{ left: place.x * S, top: place.y * S, "--z": `${place.z * S}px` } as CSSProperties}>
            <i className={styles.ring} />
            <i className={styles.beam} />
            <div className={styles.billboard}>
              <Link href={`/stations/${spot.key}`} draggable={false} className={styles.card} aria-label={`${place.title}: ${spot.value}${spot.unit ?? ""} · ${STATE_LABEL[spot.dataState]}`}>
                <span className={styles.cardTitle}>{place.title}</span>
                <strong className={styles.cardValue}>{spot.value}{spot.unit ? <small>{spot.unit}</small> : null}</strong>
                <span className={styles.cardDetail}>{spot.detail}</span>
                <span className={styles.cardState}><i />{STATE_LABEL[spot.dataState]} · {place.place}</span>
              </Link>
            </div>
          </div>;
        })}
      </div>

      <div className={styles.legend} aria-hidden="true">
        <span><i className={styles.legendPipe} />น้ำจากบ่อสุดท้าย → หอโรยยาง</span>
        <span><i className={styles.legendTrolley} />เก๊ะ หอโรยยาง → เตา</span>
        <span><i className={styles.legendProduct} />ยางแห้ง → Press → บรรจุ</span>
      </div>
      <p className={styles.compass} aria-hidden="true">MASTER PLAN AJ2 · QD-R-A192/3</p>
    </div>
  </section>;
}
