import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.env.PCC_INTERNAL_URL ?? "http://pcc:3000";
const token = process.env.PCC_SYNC_TOKEN;
const healthPath = process.env.RACK_SYNC_HEALTH_PATH ?? "/tmp/rack-sync-last-success";
const requestedInterval = Number(process.env.SYNC_INTERVAL_SECONDS ?? 10);
const intervalSeconds = Number.isFinite(requestedInterval)
  ? Math.min(300, Math.max(5, requestedInterval))
  : 10;

export function isHealthy() {
  try {
    const lastSuccess = Number(readFileSync(healthPath, "utf8"));
    const maxAgeMs = Math.max(60_000, intervalSeconds * 3_000);
    const ageMs = Date.now() - lastSuccess;
    if (Number.isFinite(lastSuccess) && ageMs >= -5_000 && ageMs <= maxAgeMs) {
      return true;
    }
  } catch {
    // No successful sync has been recorded yet.
  }
  return false;
}

export async function reconcile(fetchImpl = fetch) {
  const startedAt = Date.now();
  try {
    const response = await fetchImpl(`${baseUrl}/api/integrations/rack-monitor/sync`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(8000),
    });
    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      writeFileSync(healthPath, String(Date.now()), "utf8");
    }
    console.log(JSON.stringify({
      level: response.ok ? "INFO" : "WARN",
      event: response.ok ? "rack_sync_complete" : "rack_sync_failed",
      status: response.status,
      duration_ms: Date.now() - startedAt,
      result: body,
    }));
    return response.ok;
  } catch (error) {
    console.error(JSON.stringify({
      level: "WARN",
      event: "rack_sync_unreachable",
      duration_ms: Date.now() - startedAt,
      error_type: error instanceof Error ? error.name : "UnknownError",
    }));
    return false;
  }
}

async function run() {
  if (process.argv.includes("--healthcheck")) {
    process.exit(isHealthy() ? 0 : 1);
  }
  if (!token) {
    console.error(JSON.stringify({ level: "ERROR", event: "sync_token_missing" }));
    process.exit(1);
  }
  let stopping = false;
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => {
      stopping = true;
    });
  }
  while (!stopping) {
    await reconcile();
    await new Promise((resolve) => setTimeout(resolve, intervalSeconds * 1000));
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await run();
}
