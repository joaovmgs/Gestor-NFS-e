import assert from "node:assert/strict";
import { readFile, rm } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { downloadFile } from "./http-download.js";

test("streams a download directly to disk", async () => {
  const payload = Buffer.alloc(2 * 1024 * 1024, "a");
  const server = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "application/zip" });
    response.end(payload);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Servidor de teste sem porta.");
  const destination = path.join(tmpdir(), `gestor-nfse-download-${Date.now()}.zip`);

  try {
    await downloadFile(`http://127.0.0.1:${address?.port}/documents.zip`, destination);
    assert.deepEqual(await readFile(destination), payload);
  } finally {
    server.close();
    await rm(destination, { force: true });
  }
});

test("returns the API error detail", async () => {
  const server = createServer((_request, response) => {
    response.writeHead(500, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ detail: "Falha ao gerar um PDF." }));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Servidor de teste sem porta.");

  try {
    await assert.rejects(
      downloadFile(
        `http://127.0.0.1:${address?.port}/documents.zip`,
        path.join(tmpdir(), "unused-download.zip")
      ),
      /Falha ao gerar um PDF/
    );
  } finally {
    server.close();
  }
});
