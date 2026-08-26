export interface UpdateStatus {
  currentVersion: string;
  latestVersion?: string;
  updateAvailable: boolean;
  releaseUrl?: string;
  publishedAt?: string;
  checkedAt: string;
  error?: string;
}

interface GithubRelease {
  tag_name?: unknown;
  published_at?: unknown;
}

const latestReleaseApiUrl =
  "https://api.github.com/repos/joaovmgs/Gestor-NFS-e/releases/latest";
const releasePageBaseUrl =
  "https://github.com/joaovmgs/Gestor-NFS-e/releases/tag/";

function versionParts(version: string): number[] | null {
  const match = version.trim().match(/^v?(\d+(?:\.\d+){1,3})(?:[-+].*)?$/iu);
  return match ? match[1].split(".").map(Number) : null;
}

export function isNewerVersion(candidate: string, current: string): boolean {
  const candidateParts = versionParts(candidate);
  const currentParts = versionParts(current);
  if (!candidateParts || !currentParts) return false;

  const length = Math.max(candidateParts.length, currentParts.length);
  for (let index = 0; index < length; index += 1) {
    const candidatePart = candidateParts[index] ?? 0;
    const currentPart = currentParts[index] ?? 0;
    if (candidatePart !== currentPart) return candidatePart > currentPart;
  }
  return false;
}

function displayVersion(version: string): string {
  return version.trim().replace(/^v/iu, "");
}

export async function fetchLatestUpdate(
  currentVersion: string,
  fetcher: typeof fetch = fetch
): Promise<UpdateStatus> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await fetcher(latestReleaseApiUrl, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": `Gestor-NFSe/${currentVersion}`,
        "X-GitHub-Api-Version": "2022-11-28"
      },
      signal: controller.signal
    });
    if (!response.ok) {
      throw new Error(`GitHub respondeu com o código ${response.status}.`);
    }

    const release = await response.json() as GithubRelease;
    if (typeof release.tag_name !== "string" || !versionParts(release.tag_name)) {
      throw new Error("O GitHub retornou uma versão inválida.");
    }

    const latestVersion = displayVersion(release.tag_name);
    return {
      currentVersion,
      latestVersion,
      updateAvailable: isNewerVersion(latestVersion, currentVersion),
      releaseUrl: `${releasePageBaseUrl}${encodeURIComponent(release.tag_name)}`,
      publishedAt:
        typeof release.published_at === "string" ? release.published_at : undefined,
      checkedAt: new Date().toISOString()
    };
  } finally {
    clearTimeout(timeout);
  }
}
