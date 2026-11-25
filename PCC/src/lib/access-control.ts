export const PCC_ROLES = ["admin", "operator", "viewer"] as const;
export type PccRole = (typeof PCC_ROLES)[number];

export const PCC_CAPABILITIES = [
  "dashboard:view",
  "reports:view",
  "incidents:view",
  "incidents:acknowledge",
  "incidents:resolve",
  "devices:view",
  "devices:configure",
  "users:manage",
  "audit:view",
] as const;
export type PccCapability = (typeof PCC_CAPABILITIES)[number];

const ROLE_CAPABILITIES: Record<PccRole, ReadonlySet<PccCapability>> = {
  admin: new Set(PCC_CAPABILITIES),
  operator: new Set([
    "dashboard:view",
    "reports:view",
    "incidents:view",
    "incidents:acknowledge",
    "incidents:resolve",
    "devices:view",
  ]),
  viewer: new Set([
    "dashboard:view",
    "reports:view",
    "incidents:view",
    "devices:view",
  ]),
};

export type AuthClaims = {
  sub?: unknown;
  email?: unknown;
  app_metadata?: unknown;
  user_metadata?: unknown;
};

export function roleFromClaims(claims: AuthClaims | null | undefined): PccRole | null {
  if (!claims?.sub || typeof claims.sub !== "string") return null;
  const metadata = claims.app_metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return null;
  const role = (metadata as Record<string, unknown>).pcc_role;
  return PCC_ROLES.find((item) => item === role) ?? null;
}

export function hasCapability(role: PccRole | null | undefined, capability: PccCapability) {
  return role ? ROLE_CAPABILITIES[role].has(capability) : false;
}

export function assertCapability(role: PccRole | null | undefined, capability: PccCapability) {
  if (!hasCapability(role, capability)) throw new Error("forbidden");
}

export function capabilitiesFor(role: PccRole) {
  return [...ROLE_CAPABILITIES[role]];
}
