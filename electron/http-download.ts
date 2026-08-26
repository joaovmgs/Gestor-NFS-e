import { createWriteStream } from "node:fs";
import { Readable, Transform } from "node:stream";
import type { ReadableStream } from "node:stream/web";
import { pipeline } from "node:stream/promises";

export interface DownloadProgress {
  downloadedBytes: number;
  totalBytes?: number;
  percent?: number;
}

export async function downloadFile(
  url: string,
  destination: string,
  headers: Record<string, string> = {},
  onProgress?: (progress: DownloadProgress) => void
): Promise<void> {
  const response = await fetch(url, { headers, redirect: "follow" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: undefined })) as {
      detail?: unknown;
    };
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Falha no download: HTTP ${response.status}.`
    );
  }
  if (!response.body) throw new Error("O servidor retornou um arquivo vazio.");

  const contentLength = Number(response.headers.get("content-length"));
  const totalBytes = Number.isFinite(contentLength) && contentLength > 0
    ? contentLength
    : undefined;
  let downloadedBytes = 0;
  let lastProgressAt = 0;
  const progress = new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      downloadedBytes += chunk.length;
      const now = Date.now();
      if (onProgress && (now - lastProgressAt >= 200 || downloadedBytes === totalBytes)) {
        lastProgressAt = now;
        onProgress({
          downloadedBytes,
          totalBytes,
          percent: totalBytes
            ? Math.min(100, Math.round((downloadedBytes / totalBytes) * 100))
            : undefined
        });
      }
      callback(null, chunk);
    }
  });

  await pipeline(
    Readable.fromWeb(response.body as ReadableStream),
    progress,
    createWriteStream(destination)
  );
  onProgress?.({
    downloadedBytes,
    totalBytes,
    percent: totalBytes ? 100 : undefined
  });
}
