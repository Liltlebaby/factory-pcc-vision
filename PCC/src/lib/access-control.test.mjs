import assert from "node:assert/strict";
import test from "node:test";
import { capabilitiesFor, hasCapability, roleFromClaims } from "./access-control.ts";

test("reads role only from app_metadata", () => {
  assert.equal(roleFromClaims({ sub: "user-1", app_metadata: { pcc_role: "operator" } }), "operator");
  assert.equal(roleFromClaims({ sub: "user-1", user_metadata: { pcc_role: "admin" } }), null);
  assert.equal(roleFromClaims({ sub: "user-1", app_metadata: { pcc_role: "unknown" } }), null);
  assert.equal(roleFromClaims({ app_metadata: { pcc_role: "admin" } }), null);
});

test("viewer is read-only and operator can handle incidents", () => {
  assert.equal(hasCapability("viewer", "incidents:view"), true);
  assert.equal(hasCapability("viewer", "incidents:acknowledge"), false);
  assert.equal(hasCapability("operator", "incidents:acknowledge"), true);
  assert.equal(hasCapability("operator", "incidents:resolve"), true);
  assert.equal(hasCapability("operator", "devices:configure"), false);
});

test("admin receives every declared capability", () => {
  assert.equal(capabilitiesFor("admin").length, 9);
  assert.equal(hasCapability("admin", "users:manage"), true);
  assert.equal(hasCapability("admin", "audit:view"), true);
});
