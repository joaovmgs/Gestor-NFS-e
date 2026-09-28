import assert from "node:assert/strict";
import test from "node:test";
import { DominioMonitor } from "./dominio-monitor.js";

test("retries after disconnect and preserves the last successful result", async () => {
  let now = 0;
  let calls = 0;
  const monitor = new DominioMonitor(async () => {
    calls++;
    if (calls === 2) throw new Error("network unavailable");
    return { matched: calls, issues: [] };
  }, () => now);
  await monitor.refresh();
  assert.equal(monitor.status.state, "connected");
  now = 60_000;
  await monitor.refresh();
  assert.equal(monitor.status.state, "offline");
  assert.equal(monitor.status.result?.matched, 1);
  await monitor.refresh();
  assert.equal(calls, 2);
  now = 120_000;
  await monitor.refresh();
  assert.equal(monitor.status.state, "connected");
  assert.equal(monitor.status.result?.matched, 3);
});

test("rechecks missing companies and coalesces simultaneous refresh requests", async () => {
  let finish!: () => void;
  const gate = new Promise<void>(resolve => { finish = resolve; });
  let calls = 0;
  let now = 0;
  const monitor = new DominioMonitor(async () => {
    calls++;
    await gate;
    return { matched: calls - 1, issues: calls === 1 ? [{ cnpj: "cnpj", message: "missing" }] : [] };
  }, () => now);
  const one = monitor.refresh();
  const two = monitor.refresh(true);
  finish();
  await Promise.all([one, two]);
  assert.equal(calls, 1);
  assert.equal(monitor.status.result?.issues.length, 1);
  now = 60_000;
  await monitor.refresh();
  assert.equal(monitor.status.result?.issues.length, 0);
  assert.equal(monitor.status.result?.matched, 1);
});

test("disabled integration remains inactive and can be resumed", async () => {
  let enabled = false;
  const monitor = new DominioMonitor(async () => enabled ? { matched: 0, issues: [] } : null);
  await monitor.refresh();
  assert.equal(monitor.status.state, "disabled");
  enabled = true;
  await monitor.refresh(true);
  assert.equal(monitor.status.state, "connected");
});

test("background refresh waits while new credentials are being configured", async () => {
  let finish!: () => void;
  const gate = new Promise<void>(resolve => { finish = resolve; });
  let calls = 0;
  const monitor = new DominioMonitor(async () => {
    calls++;
    return { matched: 0, issues: [] };
  });
  const configuring = monitor.configure(async () => {
    await gate;
    return { matched: 2, issues: [] };
  });
  await Promise.resolve();
  await Promise.resolve();
  const refresh = monitor.refresh(true);
  finish();
  await Promise.all([configuring, refresh]);
  assert.equal(calls, 0);
  assert.equal(monitor.status.result?.matched, 2);
});
