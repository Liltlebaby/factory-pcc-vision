import assert from "node:assert/strict";
import test from "node:test";
import { deriveSystemReadiness } from "./system-health.ts";

const up = { ok: true, ready: true, latency_ms: 12 };
const cameraOffline = { ok: true, ready: false, latency_ms: 8, reason: "camera_not_ready" };
const down = { ok: false, latency_ms: 30, reason: "unreachable" };

test("is ready when database and Vision Monitor are ready", () => {
  const result = deriveSystemReadiness(up, up, false);
  assert.equal(result.ready, true);
  assert.equal(result.status, "ready");
});

test("keeps PCC routable in degraded mode when the camera is optional", () => {
  const result = deriveSystemReadiness(up, cameraOffline, false);
  assert.equal(result.ready, true);
  assert.equal(result.status, "degraded");
});

test("fails readiness when the database is unavailable", () => {
  const result = deriveSystemReadiness(down, up, false);
  assert.equal(result.ready, false);
  assert.equal(result.status, "not_ready");
});

test("can require Vision Monitor for strict deployments", () => {
  const result = deriveSystemReadiness(up, cameraOffline, true);
  assert.equal(result.ready, false);
  assert.equal(result.status, "not_ready");
});
