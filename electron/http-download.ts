import { createWriteStream } from "node:fs";
import { get } from "node:http";
import { pipeline } from "node:stream/promises";

export async function downloadFile(
  url: string,
  destination: string,
  headers: Record<string, string> = {}
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const request = get(url, { headers }, (response) => {
      const status = response.statusCode ?? 0;
      if (status < 200 || status >= 300) {
        response.setEncoding("utf8");
        let body = "";
        response.on("data", (chunk: string) => {
          body = `${body}${chunk}`.slice(-10_000);
        });
        response.on("end", () => {
          try {
            const parsed = JSON.parse(body) as { detail?: unknown };
            reject(new Error(
              typeof parsed.detail === "string"
                ? parsed.detail
                : `Falha no download: HTTP ${status}.`
            ));
          } catch {
            reject(new Error(`Falha no download: HTTP ${status}.`));
          }
        });
        return;
      }

      pipeline(response, createWriteStream(destination))
        .then(() => resolve())
        .catch(reject);
    });
    request.on("error", reject);
  });
}
