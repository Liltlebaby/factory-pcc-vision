import assert from "node:assert/strict";
import { existsSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const healthPath = join(fileURLToPath(new URL(".", import.meta.url)),
  `.rack-sync-health-${process.pid}-${Date.now()}`);
process.env.PCC_SYNC_TOKEN = "test-token";
process.env.PCC_INTERNAL_URL = "http://pcc.test:3000";
process.env.RACK_SYNC_HEALTH_PATH = healthPath;
const { isHealthy, reconcile } = await import("../rack-sync.mjs");

test("sync worker records health only after a successful reconcile", async () => {
  try {
    assert.equal(isHealthy(), false);
    const ok = await reconcile(async (url, request) => {
      assert.equal(url, "http://pcc.test:3000/api/integrations/rack-monitor/sync");
      assert.equal(request.method, "POST");
      assert.equal(request.headers.Authorization, "Bearer test-token");
      return { ok: true, status: 200, json: async () => ({ stored: 1 }) };
    });
    assert.equal(ok, true);
    assert.equal(existsSync(healthPath), true);
    assert.equal(isHealthy(), true);
    writeFileSync(healthPath, String(Date.now() - 120_000));
    assert.equal(isHealthy(), false);
  } finally {
    rmSync(healthPath, { force: true });
  }
});

test("failed sync does not refresh health", async () => {
  try {
    assert.equal(await reconcile(async () => ({
      ok: false, status: 503, json: async () => ({ error: "unavailable" }),
    })), false);
    assert.equal(isHealthy(), false);
    assert.equal(await reconcile(async () => { throw new Error("network down"); }), false);
    assert.equal(isHealthy(), false);
  } finally {
    rmSync(healthPath, { force: true });
  }
});
