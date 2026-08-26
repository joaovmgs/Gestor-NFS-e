import assert from "node:assert/strict";
import test from "node:test";

import { fetchLatestUpdate, isNewerVersion } from "./update-check.js";

test("compares semantic release versions", () => {
  assert.equal(isNewerVersion("v0.1.9", "0.1.8"), true);
  assert.equal(isNewerVersion("v0.2.0", "0.1.99"), true);
  assert.equal(isNewerVersion("v1.0.0", "1.0.0"), false);
  assert.equal(isNewerVersion("v0.1.7", "0.1.8"), false);
  assert.equal(isNewerVersion("release-2", "0.1.8"), false);
});

test("maps the latest GitHub release to an available update", async () => {
  const status = await fetchLatestUpdate("0.1.8", async () =>
    new Response(JSON.stringify({
      tag_name: "v0.1.9",
      published_at: "2026-08-26T12:00:00Z"
    }), { status: 200 })
  );

  assert.equal(status.updateAvailable, true);
  assert.equal(status.latestVersion, "0.1.9");
  assert.equal(
    status.releaseUrl,
    "https://github.com/joaovmgs/Gestor-NFS-e/releases/tag/v0.1.9"
  );
});

test("does not offer the installed release again", async () => {
  const status = await fetchLatestUpdate("0.1.8", async () =>
    new Response(JSON.stringify({ tag_name: "v0.1.8" }), { status: 200 })
  );

  assert.equal(status.updateAvailable, false);
});

test("rejects invalid GitHub release payloads", async () => {
  await assert.rejects(
    fetchLatestUpdate("0.1.8", async () =>
      new Response(JSON.stringify({ tag_name: "latest" }), { status: 200 })
    ),
    /versão inválida/
  );
});
