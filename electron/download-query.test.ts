import assert from "node:assert/strict";
import test from "node:test";

import { resolveDownloadQuery } from "./download-query.js";

test("resolves the current IPC argument format", () => {
  assert.deepEqual(
    resolveDownloadQuery(
      "12345678000190",
      "2026-07-01",
      "2026-07-31",
      "recebida"
    ),
    {
      cnpj: "12345678000190",
      startDate: "2026-07-01",
      endDate: "2026-07-31",
      direction: "recebida"
    }
  );
});

test("resolves the legacy window object format", () => {
  assert.equal(
    resolveDownloadQuery({
      cnpj: "12345678000190",
      startDate: "2026-06-01",
      endDate: "2026-06-30",
      direction: "emitida"
    }).direction,
    "emitida"
  );
});

test("falls back to the last applied filter", () => {
  const result = resolveDownloadQuery(
    "12345678000190",
    undefined,
    undefined,
    undefined,
    {
      startDate: "2026-05-01",
      endDate: "2026-05-31",
      direction: "recebida"
    }
  );
  assert.equal(result.startDate, "2026-05-01");
  assert.equal(result.endDate, "2026-05-31");
  assert.equal(result.direction, "recebida");
});

test("uses the current month when no period was supplied or applied", () => {
  const result = resolveDownloadQuery("12345678000190");
  assert.match(result.startDate, /^\d{4}-\d{2}-01$/);
  assert.match(result.endDate, /^\d{4}-\d{2}-\d{2}$/);
  assert.equal(result.direction, "emitida");
});

test("accepts snake case filters from older renderers", () => {
  const result = resolveDownloadQuery({
    cnpj: "12345678000190",
    data_inicial: "2026-04-01",
    data_final: "2026-04-30",
    tipo: "recebida"
  });
  assert.equal(result.startDate, "2026-04-01");
  assert.equal(result.endDate, "2026-04-30");
  assert.equal(result.direction, "recebida");
});
