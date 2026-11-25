export type Status = "GREEN" | "YELLOW" | "RED" | "SENSOR_ERROR";

export type MeasurementType = "WEIGHT" | "TEMPERATURE" | "POND_TEMPERATURE";

export type Source =
  | "SCALE"
  | "BURNER"
  | "RECORDER"
  | "THERMOMETER"
  | "POND_SENSOR";

export type IncidentSource = "WEIGHT" | "TEMPERATURE" | "POND";

export type IncidentStatus =
  | "OPEN"
  | "ACKNOWLEDGED"
  | "IN_PROGRESS"
  | "VERIFYING"
  | "CLOSED";

export type Severity = "WARNING" | "CRITICAL";

/** measurements */
export interface Measurement {
  id: string;
  furnaceId: string;
  workOrderId: string;
  lotId: string;
  measurementType: MeasurementType;
  source: Source;
  value: number;
  unit: string;
  measuredAt: number;
  qualityStatus: Status;
}

/** comparisons — ค่าที่ระบบคำนวณแล้ว ไม่ใช่ค่าดิบ */
export interface Comparison {
  id: string;
  measurementId: string;
  referenceValue: number;
  actualValue: number;
  delta: number;
  status: Status;
  lowerLimit: number;
  upperLimit: number;
  warningLimit: number;
  ruleCode: string;
  detectedAt: number;
}

export interface WeightSample {
  lotNo: number;
  measurement: Measurement;
  comparison: Comparison;
  deviation: number;
}

export interface TempSample {
  tick: number;
  measuredAt: number;
  actual: number;
  burner: number;
  recorder: number;
  deltaBurner: number;
  deltaRecorder: number;
  worstError: number;
  status: Status;
  ruleCode: string;
  swing15: number;
}

export interface PondSample {
  tick: number;
  measuredAt: number;
  value: number;
  /** Optional for samples persisted before pH was added. */
  ph?: number;
  status: Status;
  ruleCode: string;
}

export interface AuditEntry {
  at: number;
  actor: string;
  action: string;
  detail?: string;
}

export interface Incident {
  id: string;
  source: IncidentSource;
  sourceMeasurementId: string;
  ruleCode: string;
  detectedAt: number;
  issue: string;
  severity: Severity;
  impactQuality: boolean;
  impactSmell: boolean;
  impactFail: boolean;
  aiSuggestion: string[];
  task: string;
  owner: string;
  status: IncidentStatus;
  slaMinutes: number;
  deadline: number;
  slaBreached: boolean;
  escalated: boolean;
  requiresApproval: boolean;
  approvedBy?: string;
  approvedAt?: number;
  closedAt?: number;
  verifyRemaining: number;
  auditLog: AuditEntry[];
  snapshot: string;
}

export interface SystemEvent {
  id: string;
  at: number;
  level: Status;
  source: IncidentSource | "SYSTEM";
  ruleCode: string;
  message: string;
  incidentId?: string;
}

export interface Signal {
  ruleCode: string;
  severity: Severity;
  message: string;
  opensIncident: boolean;
}

export interface CorrelationInsight {
  at: number;
  weightNote: string;
  tempNote: string;
  suggestion: string;
}
