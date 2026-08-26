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
      published_at: "2026-08-26T12:00:00Z",
      assets: [{
        name: "Gestor-NFSe-Setup-0.1.9.exe",
        browser_download_url:
          "https://github.com/joaovmgs/Gestor-NFS-e/releases/download/v0.1.9/Gestor-NFSe-Setup-0.1.9.exe",
        size: 175_000_000,
        digest: `sha256:${"a".repeat(64)}`
      }]
    }), { status: 200 })
  );

  assert.equal(status.updateAvailable, true);
  assert.equal(status.latestVersion, "0.1.9");
  assert.equal(
    status.releaseUrl,
    "https://github.com/joaovmgs/Gestor-NFS-e/releases/tag/v0.1.9"
  );
  assert.equal(status.installerName, "Gestor-NFSe-Setup-0.1.9.exe");
  assert.equal(status.installerSize, 175_000_000);
  assert.equal(status.installerDigest, `sha256:${"a".repeat(64)}`);
});

test("ignores installer URLs outside the official repository", async () => {
  const status = await fetchLatestUpdate("0.1.8", async () =>
    new Response(JSON.stringify({
      tag_name: "v0.1.9",
      assets: [{
        name: "Gestor-NFSe-Setup-0.1.9.exe",
        browser_download_url: "https://example.com/Gestor-NFSe-Setup-0.1.9.exe"
      }]
    }), { status: 200 })
  );

  assert.equal(status.updateAvailable, true);
  assert.equal(status.installerUrl, undefined);
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
