import assert from "node:assert/strict";
import test from "node:test";

import { SequentialTaskQueue } from "./task-queue.js";

test("processes export jobs sequentially", async () => {
  const order: string[] = [];
  let releaseFirst: (() => void) | undefined;
  const firstGate = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  let finished: (() => void) | undefined;
  const allFinished = new Promise<void>((resolve) => {
    finished = resolve;
  });
  const queue = new SequentialTaskQueue<string>(
    async (item) => {
      order.push(`start:${item}`);
      if (item === "A") await firstGate;
      order.push(`end:${item}`);
      if (item === "B") finished?.();
    },
    () => undefined,
    (item) => item
  );

  assert.equal(queue.enqueue("A"), 1);
  assert.equal(queue.enqueue("B"), 2);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(order, ["start:A"]);
  assert.equal(queue.snapshot().activeId, "A");
  assert.deepEqual(queue.snapshot().pendingIds, ["B"]);
  releaseFirst?.();
  await allFinished;
  assert.deepEqual(order, ["start:A", "end:A", "start:B", "end:B"]);
});

test("removes pending jobs by id without stopping the active job", async () => {
  const order: string[] = [];
  let releaseFirst: (() => void) | undefined;
  const firstGate = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  const queue = new SequentialTaskQueue<string>(
    async (item) => {
      order.push(`start:${item}`);
      if (item === "A") await firstGate;
      order.push(`end:${item}`);
    },
    () => undefined,
    (item) => item
  );

  queue.enqueue("A");
  queue.enqueue("B");
  queue.enqueue("B");
  queue.enqueue("C");
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(queue.removePendingById("B"), 2);
  assert.equal(queue.snapshot().activeId, "A");
  assert.deepEqual(queue.snapshot().pendingIds, ["C"]);

  releaseFirst?.();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(order, ["start:A", "end:A", "start:C", "end:C"]);
});
