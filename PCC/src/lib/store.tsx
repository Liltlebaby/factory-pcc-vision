"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
} from "react";
import {
  FURNACE,
  OWNERS,
  POND_SPEC,
  PLAYBOOK,
  RULE_PRIORITY,
  SECONDS_PER_TICK,
  SERIES_LIMIT,
  TEMP_SPEC,
  TICK_MS,
  WEIGHT_SPEC,
  WEIGHT_TICKS_PER_SAMPLE,
  DEMO_SENSORS,
} from "./config";
import {
  classifyTemp,
  classifyPondTemp,
  classifyWeight,
  compareTemp,
  fmtDelta,
  healthPercent,
  pondSignals,
  recorderSwing,
  tempSignals,
  weightSignals,
} from "./engine";
import { nextPondPh, nextPondTemp, nextTemp, nextWeight, type Scenario } from "./simulator";
import type {
  CorrelationInsight,
  Incident,
  IncidentSource,
  PondSample,
  Signal,
  SystemEvent,
  TempSample,
  WeightSample,
} from "./types";

/** ฐานเวลาคงที่ เพื่อให้ค่าเริ่มต้นตรงกันทั้งฝั่ง server และ client */
const BASE_TIME = new Date("2026-09-04T08:00:00+07:00").getTime();

export const CURRENT_USER = "สมชาย (หัวหน้างานเตา A)";

interface State {
  /** อ่านข้อมูลที่เก็บไว้เสร็จแล้วหรือยัง ใช้กันหน้าจอโชว์ "ไม่พบข้อมูล" ตอนกำลังกู้คืน */
  hydrated: boolean;
  running: boolean;
  tick: number;
  scenario: Scenario;
  scenarioStartTick: number;
  seq: number;
  weightSeries: WeightSample[];
  tempSeries: TempSample[];
  pondSeries: PondSample[];
  incidents: Incident[];
  events: SystemEvent[];
  correlation: CorrelationInsight | null;
}

type Action =
  | { type: "TICK" }
  | { type: "SET_RUNNING"; running: boolean }
  | { type: "SET_SCENARIO"; scenario: Scenario }
  | { type: "ACK"; id: string }
  | { type: "APPROVE"; id: string }
  | { type: "RESOLVE"; id: string }
  | { type: "ESCALATE"; id: string }
  | { type: "HYDRATE"; state: State }
  | { type: "HYDRATE_EMPTY" }
  | { type: "RESET" };

const initialState: State = {
  hydrated: false,
  running: true,
  tick: 0,
  scenario: "NORMAL",
  scenarioStartTick: 0,
  seq: 1,
  weightSeries: [],
  tempSeries: [],
  pondSeries: [],
  incidents: [],
  events: [],
  correlation: null,
};

function simTime(tick: number) {
  return BASE_TIME + tick * SECONDS_PER_TICK * 1000;
}

function tail<T>(arr: T[]) {
  return arr.length > SERIES_LIMIT ? arr.slice(arr.length - SERIES_LIMIT) : arr;
}

function sourceOfRule(ruleCode: string): IncidentSource {
  if (ruleCode.startsWith("POND")) return "POND";
  return ruleCode.startsWith("TEMP") ? "TEMPERATURE" : "WEIGHT";
}

function priorityOf(ruleCode: string) {
  return RULE_PRIORITY[ruleCode] ?? 0;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "SET_RUNNING":
      return { ...state, running: action.running };

    case "SET_SCENARIO":
      return {
        ...state,
        scenario: action.scenario,
        scenarioStartTick: state.tick,
      };

    case "HYDRATE":
      return {
        ...action.state,
        pondSeries: action.state.pondSeries ?? [],
        hydrated: true,
        running: state.running,
      };

    case "HYDRATE_EMPTY":
      return { ...state, hydrated: true };

    case "RESET":
      return { ...initialState, hydrated: true, scenario: state.scenario };

    case "TICK":
      return advance(state);

    case "ACK":
      return updateIncident(state, action.id, (incident, at) => ({
        ...incident,
        status: incident.requiresApproval ? "ACKNOWLEDGED" : "IN_PROGRESS",
        auditLog: [
          ...incident.auditLog,
          {
            at,
            actor: CURRENT_USER,
            action: "รับทราบการแจ้งเตือน",
            detail: incident.requiresApproval
              ? "รอผู้มีอำนาจอนุมัติแนวทางก่อนดำเนินการ"
              : `เริ่มดำเนินการ: ${incident.task}`,
          },
        ],
      }));

    case "APPROVE":
      return updateIncident(state, action.id, (incident, at) => ({
        ...incident,
        status: "IN_PROGRESS",
        approvedBy: CURRENT_USER,
        approvedAt: at,
        auditLog: [
          ...incident.auditLog,
          {
            at,
            actor: CURRENT_USER,
            action: "อนุมัติแนวทางแก้ไข",
            detail: incident.task,
          },
        ],
      }));

    case "RESOLVE":
      return updateIncident(state, action.id, (incident, at) => ({
        ...incident,
        status: "VERIFYING",
        verifyRemaining: 2,
        auditLog: [
          ...incident.auditLog,
          {
            at,
            actor: CURRENT_USER,
            action: "แจ้งว่าแก้ไขแล้ว",
            detail: "ระบบจะตรวจค่ารอบถัดไป 2 ครั้งก่อนปิด Incident",
          },
        ],
      }));

    case "ESCALATE":
      return updateIncident(state, action.id, (incident, at) => ({
        ...incident,
        escalated: true,
        owner: OWNERS.supervisor,
        auditLog: [
          ...incident.auditLog,
          {
            at,
            actor: CURRENT_USER,
            action: "Escalate ให้หัวหน้ากะ",
            detail: "ผู้รับผิดชอบเดิมแก้ไม่ได้ในเวลาที่กำหนด",
          },
        ],
      }));

    default:
      return state;
  }
}

function updateIncident(
  state: State,
  id: string,
  fn: (incident: Incident, at: number) => Incident,
): State {
  const at = simTime(state.tick);
  return {
    ...state,
    incidents: state.incidents.map((incident) =>
      incident.id === id ? fn(incident, at) : incident,
    ),
  };
}

function advance(state: State): State {
  const tick = state.tick + 1;
  const at = simTime(tick);
  const ticksInScenario = tick - state.scenarioStartTick;
  let seq = state.seq;
  const nextId = (prefix: string) => `${prefix}-${String(seq++).padStart(4, "0")}`;

  /** ---- Function 01: ตาชั่งหน้าเตา (ได้ค่าใหม่ทุก WEIGHT_TICKS_PER_SAMPLE รอบ) ---- */
  const previousWeight =
    state.weightSeries.length > 0
      ? state.weightSeries[state.weightSeries.length - 1].measurement.value
      : WEIGHT_SPEC.target;
  let weightSeries = state.weightSeries;
  let weightSample: WeightSample | null = null;

  if (DEMO_SENSORS.weight && tick % WEIGHT_TICKS_PER_SAMPLE === 0) {
    const sampleIndex = Math.floor(ticksInScenario / WEIGHT_TICKS_PER_SAMPLE);
    const weightValue = nextWeight(state.scenario, sampleIndex, previousWeight);
    const weightVerdict = classifyWeight(weightValue);
    const lotNo = (state.weightSeries.at(-1)?.lotNo ?? 0) + 1;
    const weightMeasurementId = nextId("MEA");

    weightSample = {
      lotNo,
      deviation: weightValue - WEIGHT_SPEC.target,
      measurement: {
        id: weightMeasurementId,
        furnaceId: FURNACE.id,
        workOrderId: FURNACE.workOrderId,
        lotId: `LOT-${String(lotNo).padStart(4, "0")}`,
        measurementType: "WEIGHT",
        source: "SCALE",
        value: weightValue,
        unit: WEIGHT_SPEC.unit,
        measuredAt: at,
        qualityStatus: weightVerdict.status,
      },
      comparison: {
        id: nextId("CMP"),
        measurementId: weightMeasurementId,
        referenceValue: WEIGHT_SPEC.target,
        actualValue: weightValue,
        delta: weightValue - WEIGHT_SPEC.target,
        status: weightVerdict.status,
        lowerLimit: WEIGHT_SPEC.lsl,
        upperLimit: WEIGHT_SPEC.usl,
        warningLimit: WEIGHT_SPEC.warningBand,
        ruleCode: weightVerdict.ruleCode,
        detectedAt: at,
      },
    };
    weightSeries = tail([...state.weightSeries, weightSample]);
  }

  /** ---- Function 02: Burner / Recorder / Digital Thermometer ---- */
  const reading = nextTemp(state.scenario, ticksInScenario);
  const { deltaBurner, deltaRecorder, worstError } = compareTemp(
    reading.actual,
    reading.burner,
    reading.recorder,
  );
  const tempVerdict = classifyTemp(worstError);
  const provisional: TempSample = {
    tick,
    measuredAt: at,
    actual: reading.actual,
    burner: reading.burner,
    recorder: reading.recorder,
    deltaBurner,
    deltaRecorder,
    worstError,
    status: tempVerdict.status,
    ruleCode: tempVerdict.ruleCode,
    swing15: 0,
  };
  const withProvisional = [...state.tempSeries, provisional];
  const tempSample: TempSample = {
    ...provisional,
    swing15: recorderSwing(
      withProvisional,
      (TEMP_SPEC.swingWindowMinutes * 60) / SECONDS_PER_TICK,
    ),
  };
  const tempSeries = tail([...state.tempSeries, tempSample]);

  /** ---- Function 03: อุณหภูมิบ่อสุดท้าย ต้องไม่เกิน 35°C ---- */
  const pondValue = nextPondTemp(state.scenario, ticksInScenario);
  const pondVerdict = classifyPondTemp(pondValue);
  const pondSample: PondSample = {
    tick,
    measuredAt: at,
    value: pondValue,
    ph: nextPondPh(tick),
    status: pondVerdict.status,
    ruleCode: pondVerdict.ruleCode,
  };
  const pondSeries = tail([...(state.pondSeries ?? []), pondSample]);

  /** ---- Rule Engine ---- */
  const signals: Signal[] = [
    // กฎน้ำหนักประเมินเฉพาะรอบที่มีการชั่งก้อนใหม่
    ...(weightSample ? weightSignals(weightSeries) : []),
    // เตายังไม่มีเซ็นเซอร์จริง ไม่ให้ค่าจำลองสร้างเหตุการณ์ปลอม
    ...(DEMO_SENSORS.furnace ? tempSignals(tempSeries) : []),
    ...pondSignals(pondSeries),
  ];

  let incidents = [...state.incidents];
  const events: SystemEvent[] = [...state.events];

  for (const signal of signals) {
    const source = sourceOfRule(signal.ruleCode);
    const activeSameSource = incidents.filter(
      (i) => i.source === source && i.status !== "CLOSED",
    );
    /** ถ้ามี Incident ที่รุนแรงเท่ากันหรือมากกว่าค้างอยู่แล้ว ไม่เปิดใบใหม่ซ้อน */
    const outranked = activeSameSource.some(
      (i) => priorityOf(i.ruleCode) >= priorityOf(signal.ruleCode),
    );
    const recentlyLogged = events.some(
      (e) => e.ruleCode === signal.ruleCode && at - e.at <= 5 * 60_000,
    );

    if (signal.opensIncident && !outranked) {
      const playbook = PLAYBOOK[signal.ruleCode];
      if (!playbook) continue;
      const incident: Incident = {
        id: nextId("INC"),
        source,
        sourceMeasurementId:
          source === "WEIGHT"
            ? (weightSample?.measurement.id ?? "-")
            : source === "POND"
              ? `POND-T${tick}`
              : `TEMP-T${tick}`,
        ruleCode: signal.ruleCode,
        detectedAt: at,
        issue: playbook.issue,
        severity: playbook.severity,
        impactQuality: playbook.impactQuality,
        impactSmell: playbook.impactSmell,
        impactFail: playbook.impactFail,
        aiSuggestion: playbook.aiSuggestion,
        task: playbook.task,
        owner: playbook.owner,
        status: "OPEN",
        slaMinutes: playbook.slaMinutes,
        deadline: at + playbook.slaMinutes * 60_000,
        slaBreached: false,
        escalated: false,
        requiresApproval: playbook.requiresApproval,
        verifyRemaining: 0,
        snapshot:
          source === "WEIGHT"
            ? `${(weightSample?.measurement.value ?? 0).toFixed(2)} kg (Target ${WEIGHT_SPEC.target.toFixed(2)} / LSL ${WEIGHT_SPEC.lsl.toFixed(2)} / USL ${WEIGHT_SPEC.usl.toFixed(2)})`
            : source === "POND"
              ? `${pondSample.value.toFixed(1)}°C (เกณฑ์ไม่เกิน ${POND_SPEC.max.toFixed(0)}°C)`
              : `Actual ${reading.actual.toFixed(1)}°C | Burner ${reading.burner.toFixed(1)}°C (${fmtDelta(deltaBurner)}) | Recorder ${reading.recorder.toFixed(1)}°C (${fmtDelta(deltaRecorder)})`,
        auditLog: [
          {
            at,
            actor: "Rule Engine",
            action: `ตรวจพบตามกฎ ${signal.ruleCode}`,
            detail: signal.message,
          },
          {
            at,
            actor: "ระบบแจ้งเตือน",
            action: `แจ้ง ${playbook.owner} ผ่าน LINE`,
            detail: `SLA ${playbook.slaMinutes} นาที — ${playbook.task}`,
          },
        ],
      };
      // ใบที่รุนแรงกว่ารวบใบเดิมของแหล่งเดียวกันเข้ามา เพื่อให้หน้าจอเหลือเรื่องเดียว
      incidents = incidents.map((existing) =>
        existing.source === source &&
        existing.status !== "CLOSED" &&
        priorityOf(existing.ruleCode) < priorityOf(signal.ruleCode)
          ? {
              ...existing,
              status: "CLOSED",
              closedAt: at,
              auditLog: [
                ...existing.auditLog,
                {
                  at,
                  actor: "ระบบ",
                  action: `รวมเข้ากับ ${incident.id}`,
                  detail: "เหตุเดียวกันถูกยกระดับเป็น Incident ที่รุนแรงกว่า",
                },
              ],
            }
          : existing,
      );
      incidents = [incident, ...incidents];
      events.push({
        id: nextId("EVT"),
        at,
        level: signal.severity === "CRITICAL" ? "RED" : "YELLOW",
        source,
        ruleCode: signal.ruleCode,
        message: signal.message,
        incidentId: incident.id,
      });
    } else if (!signal.opensIncident && !recentlyLogged) {
      events.push({
        id: nextId("EVT"),
        at,
        level: "YELLOW",
        source,
        ruleCode: signal.ruleCode,
        message: signal.message,
      });
    }
  }

  /** ---- ตรวจผลหลังแก้ แล้วปิด Incident ---- */
  incidents = incidents.map((incident) => {
    if (incident.status !== "VERIFYING") return incident;
    const ok =
      incident.source === "WEIGHT"
        ? weightSample?.comparison.status === "GREEN"
        : incident.source === "POND"
          ? pondSample.status === "GREEN"
          : tempSample.status === "GREEN";
    if (!ok) return incident;

    const remaining = incident.verifyRemaining - 1;
    if (remaining > 0) {
      return { ...incident, verifyRemaining: remaining };
    }
    events.push({
      id: nextId("EVT"),
      at,
      level: "GREEN",
      source: incident.source,
      ruleCode: incident.ruleCode,
      message: `${incident.issue} — ค่ากลับเข้าเกณฑ์ ปิด Incident ${incident.id}`,
      incidentId: incident.id,
    });
    return {
      ...incident,
      status: "CLOSED",
      verifyRemaining: 0,
      closedAt: at,
      auditLog: [
        ...incident.auditLog,
        {
          at,
          actor: "ระบบ",
          action: "ตรวจค่ารอบถัดไปแล้วกลับเข้าเกณฑ์",
          detail:
            incident.source === "WEIGHT"
              ? `ก้อนที่ ${weightSample?.lotNo} ชั่งได้ ${weightSample?.measurement.value.toFixed(2)} kg`
              : incident.source === "POND"
                ? `อุณหภูมิบ่อสุดท้าย ${pondSample.value.toFixed(1)}°C`
                : `Worst Error ${fmtDelta(tempSample.worstError)}°C`,
        },
        { at, actor: "ระบบ", action: "ปิด Incident" },
      ],
    };
  });

  /** ---- SLA เกินกำหนด → Escalate อัตโนมัติ ---- */
  incidents = incidents.map((incident) => {
    const open =
      incident.status === "OPEN" ||
      incident.status === "ACKNOWLEDGED" ||
      incident.status === "IN_PROGRESS";
    if (!open || incident.slaBreached || at <= incident.deadline) {
      return incident;
    }
    events.push({
      id: nextId("EVT"),
      at,
      level: "RED",
      source: incident.source,
      ruleCode: incident.ruleCode,
      message: `${incident.id} เกิน SLA ${incident.slaMinutes} นาที — Escalate ให้${OWNERS.supervisor}`,
      incidentId: incident.id,
    });
    return {
      ...incident,
      slaBreached: true,
      escalated: true,
      owner: OWNERS.supervisor,
      auditLog: [
        ...incident.auditLog,
        {
          at,
          actor: "ระบบ",
          action: `เกิน SLA ${incident.slaMinutes} นาที`,
          detail: `Escalate อัตโนมัติให้${OWNERS.supervisor}`,
        },
      ],
    };
  });

  /** ---- เชื่อม Weight + Temperature (ข้อเสนอ ไม่ใช่การตัดสินใจ) ---- */
  const weightTrouble = signals.find(
    (s) => s.ruleCode === "W_LOW" || s.ruleCode === "W_DRIFT",
  );
  const tempUnstable =
    tempSample.swing15 > TEMP_SPEC.swingLimit || tempSample.status !== "GREEN";
  const correlation: CorrelationInsight | null =
    weightTrouble && tempUnstable
      ? {
          at,
          weightNote: weightTrouble.message,
          tempNote: `Recorder แกว่ง ${tempSample.swing15.toFixed(1)}°C ในช่วงเวลาเดียวกัน (Worst Error ${fmtDelta(tempSample.worstError)}°C)`,
          suggestion:
            "น้ำหนักที่ลดลงเกิดพร้อมกับอุณหภูมิที่ไม่นิ่ง แนะนำให้ตรวจ Burner ก่อนปรับปริมาณโรยยาง",
        }
      : state.correlation && at - state.correlation.at <= 10 * 60_000
        ? state.correlation
        : null;

  return {
    ...state,
    tick,
    seq,
    weightSeries,
    // ปิดข้อมูลจำลองเตา = ไม่เก็บค่าลง series หน้าจอจึงแสดง "ยังไม่ติดตั้ง"
    tempSeries: DEMO_SENSORS.furnace ? tempSeries : state.tempSeries,
    pondSeries,
    incidents,
    events: events.slice(-80),
    correlation,
  };
}

interface StoreValue extends State {
  now: number;
  latestWeight?: WeightSample;
  latestTemp?: TempSample;
  latestPond?: PondSample;
  activeIncidents: Incident[];
  closedIncidents: Incident[];
  weightHealth: number;
  tempHealth: number;
  pondHealth: number;
  setScenario: (scenario: Scenario) => void;
  setRunning: (running: boolean) => void;
  reset: () => void;
  acknowledge: (id: string) => void;
  approve: (id: string) => void;
  resolve: (id: string) => void;
  escalate: (id: string) => void;
}

const StoreContext = createContext<StoreValue | null>(null);

const STORAGE_KEY = "production-control-prototype";

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  /**
   * เก็บสถานะไว้ใน sessionStorage เพื่อให้ข้อมูลจำลองไม่หายเมื่อเปิด URL อื่นตรง ๆ
   * หรือกดรีเฟรช — ระบบจริงจะอ่านจากฐานข้อมูลกลางแทน
   */
  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        dispatch({ type: "HYDRATE", state: JSON.parse(raw) as State });
      } else {
        dispatch({ type: "HYDRATE_EMPTY" });
      }
    } catch {
      // ข้อมูลจำลองเสียหาย ให้เริ่มใหม่จากค่าเริ่มต้น
      dispatch({ type: "HYDRATE_EMPTY" });
    }
  }, []);

  useEffect(() => {
    if (state.tick === 0) return;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // sessionStorage เต็มหรือถูกปิด — ข้ามการเก็บ
    }
  }, [state]);

  useEffect(() => {
    if (!state.running) return;
    const timer = window.setInterval(() => dispatch({ type: "TICK" }), TICK_MS);
    return () => window.clearInterval(timer);
  }, [state.running]);

  const setScenario = useCallback(
    (scenario: Scenario) => dispatch({ type: "SET_SCENARIO", scenario }),
    [],
  );
  const setRunning = useCallback(
    (running: boolean) => dispatch({ type: "SET_RUNNING", running }),
    [],
  );
  const reset = useCallback(() => {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ไม่มีอะไรต้องล้าง
    }
    dispatch({ type: "RESET" });
  }, []);
  const acknowledge = useCallback(
    (id: string) => dispatch({ type: "ACK", id }),
    [],
  );
  const approve = useCallback(
    (id: string) => dispatch({ type: "APPROVE", id }),
    [],
  );
  const resolve = useCallback(
    (id: string) => dispatch({ type: "RESOLVE", id }),
    [],
  );
  const escalate = useCallback(
    (id: string) => dispatch({ type: "ESCALATE", id }),
    [],
  );

  const value = useMemo<StoreValue>(() => {
    const activeIncidents = state.incidents.filter((i) => i.status !== "CLOSED");
    return {
      ...state,
      now: simTime(state.tick),
      latestWeight: state.weightSeries.at(-1),
      latestTemp: state.tempSeries.at(-1),
      latestPond: state.pondSeries.at(-1),
      activeIncidents,
      closedIncidents: state.incidents.filter((i) => i.status === "CLOSED"),
      weightHealth: healthPercent(
        state.weightSeries.map((s) => s.comparison.status),
      ),
      tempHealth: healthPercent(state.tempSeries.map((s) => s.status)),
      pondHealth: healthPercent(state.pondSeries.map((s) => s.status)),
      setScenario,
      setRunning,
      reset,
      acknowledge,
      approve,
      resolve,
      escalate,
    };
  }, [state, setScenario, setRunning, reset, acknowledge, approve, resolve, escalate]);

  return (
    <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
  );
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore ต้องอยู่ภายใน StoreProvider");
  return ctx;
}
