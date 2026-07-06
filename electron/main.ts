import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  Notification,
  safeStorage,
  Tray
} from "electron";
import { ChildProcess, execFile, spawn } from "node:child_process";
import { createServer } from "node:net";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import crypto from "node:crypto";

import {
  AppliedDownloadQuery,
  LegacyDownloadQuery,
  NoteDirection,
  resolveDownloadQuery
} from "./download-query.js";
import { QueueSnapshot, SequentialTaskQueue } from "./task-queue.js";

const execFileAsync = promisify(execFile);
let backendProcess: ChildProcess | undefined;
let backendUrl = "";
let apiToken = "";
let mainWindow: BrowserWindow | undefined;
let tray: Tray | undefined;
let isQuitting = false;
const lastDocumentQueryByCompany = new Map<string, AppliedDownloadQuery>();

app.setPath("userData", path.join(app.getPath("appData"), "nfse-desktop"));
app.setName("Gestor NFS-e");

interface WindowsCertificate {
  thumbprint: string;
  cnpj: string;
  legalName: string;
  expiresAt: string;
  issuer: string;
}

interface ExportJob {
  cnpj: string;
  companyName: string;
  startDate: string;
  endDate: string;
  direction: NoteDirection;
  destination: string;
}

interface SyncRequest {
  cnpj: string;
  password?: string;
}

interface CompanyRecord {
  cnpj: string;
  legal_name: string;
  certificate_source: "pfx" | "windows";
  certificate_reference?: string;
  last_nsu: number;
}

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 8765;
      server.close(() => resolve(port));
    });
  });
}

function projectRoot(): string {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, "..");
}

async function startBackend(): Promise<void> {
  const port = await freePort();
  apiToken = crypto.randomBytes(32).toString("hex");
  backendUrl = `http://127.0.0.1:${port}`;
  const python = app.isPackaged
    ? path.join(process.resourcesPath, "backend", "gestor-nfse-backend.exe")
    : path.join(projectRoot(), ".venv", "Scripts", "python.exe");
  const packagedWeasyRoot = path.join(process.resourcesPath, "weasyprint");
  const packagedWeasyBin = path.join(packagedWeasyRoot, "bin");
  const backendEnvironment = {
    ...process.env,
    NFSE_API_TOKEN: apiToken,
    NFSE_DATA_DIR: app.getPath("userData"),
    NFSE_DEFAULT_NOTES_DIR: path.join(app.getPath("documents"), "Gestor NFS-e"),
    PYTHONPATH: path.join(projectRoot(), "backend", "src"),
    ...(app.isPackaged
      ? {
          PATH: `${packagedWeasyBin}${path.delimiter}${process.env.PATH ?? ""}`,
          WEASYPRINT_DLL_DIRECTORIES: packagedWeasyBin,
          FONTCONFIG_FILE: path.join(packagedWeasyRoot, "etc", "fonts", "fonts.conf")
        }
      : {})
  };
  const fallbackPython = process.platform === "win32" ? "python" : "python3";
  const backendArguments = app.isPackaged
    ? ["--port", String(port)]
    : ["-m", "nfse_desktop", "--port", String(port)];
  let backendError = "";
  backendProcess = spawn(
    python,
    backendArguments,
    {
      cwd: path.join(projectRoot(), "backend"),
      env: backendEnvironment,
      windowsHide: true
    }
  );
  backendProcess.stderr?.on("data", (chunk: Buffer) => {
    backendError = `${backendError}${chunk.toString("utf8")}`.slice(-4000);
  });
  backendProcess.once("error", (error) => {
    backendError = error.message;
    if (app.isPackaged) return;
    backendProcess = spawn(
      fallbackPython,
      ["-m", "nfse_desktop", "--port", String(port)],
      {
        cwd: path.join(projectRoot(), "backend"),
        env: backendEnvironment,
        windowsHide: true
      }
    );
    backendProcess.stderr?.on("data", (chunk: Buffer) => {
      backendError = `${backendError}${chunk.toString("utf8")}`.slice(-4000);
    });
  });

  for (let attempt = 0; attempt < 150; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 200));
    if (backendProcess.exitCode !== null) {
      throw new Error(
        `O serviço local foi encerrado durante a inicialização. ${backendError}`.trim()
      );
    }
    try {
      const response = await fetch(`${backendUrl}/health`);
      if (response.ok) return;
    } catch {
      // Backend ainda esta iniciando.
    }
  }
  throw new Error(
    `O serviço local não iniciou no tempo esperado. ${backendError}`.trim()
  );
}

async function api<T>(route: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Nfse-Token", apiToken);
  const response = await fetch(`${backendUrl}${route}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg ?? JSON.stringify(item)).join("; ")
      : typeof detail === "string"
        ? detail
        : "Falha no servico local.";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function credentialPath(cnpj: string): string {
  return path.join(app.getPath("userData"), "credentials", `${cnpj}.bin`);
}

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, milliseconds));

async function saveCredential(cnpj: string, password: string, pfx: Buffer): Promise<string> {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error("A protecao de credenciais do Windows nao esta disponivel.");
  }
  const encrypted = safeStorage.encryptString(
    JSON.stringify({ password, pfx: pfx.toString("base64") })
  );
  const target = credentialPath(cnpj);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, encrypted);
  return target;
}

async function removeCredential(cnpj: string): Promise<void> {
  await rm(credentialPath(cnpj), { force: true });
}

async function readCredential(cnpj: string): Promise<{ password: string; pfx: Buffer } | null> {
  try {
    const encrypted = await readFile(credentialPath(cnpj));
    const parsed = JSON.parse(safeStorage.decryptString(encrypted)) as {
      password: string;
      pfx: string;
    };
    return { password: parsed.password, pfx: Buffer.from(parsed.pfx, "base64") };
  } catch {
    return null;
  }
}

async function listWindowsCertificates(): Promise<WindowsCertificate[]> {
  const helper = windowsHelperPath();
  const { stdout } = await execFileAsync(helper, ["list"], { windowsHide: true });
  return JSON.parse(stdout) as WindowsCertificate[];
}

async function showSyncNotification(companyName: string, downloaded: number): Promise<void> {
  await showDesktopNotification(
    "Sincronização concluída",
    downloaded > 0
      ? `${companyName}: ${downloaded} documento(s) processado(s).`
      : `${companyName}: as notas já estão atualizadas.`
  );
}

async function showDesktopNotification(title: string, body: string): Promise<void> {
  const settings = await api<{ notifications_enabled: boolean }>("/settings");
  if (!settings.notifications_enabled || !Notification.isSupported()) return;
  new Notification({
    title,
    body,
    silent: false
  }).show();
}

function broadcastExportQueue(snapshot: QueueSnapshot): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("exports:status", snapshot);
  }
}

async function processExportJob(job: ExportJob): Promise<void> {
  const query = new URLSearchParams({
    data_inicial: job.startDate,
    data_final: job.endDate,
    tipo: job.direction
  });
  try {
    const response = await fetch(
      `${backendUrl}/companies/${job.cnpj}/documents.zip?${query.toString()}`,
      { headers: { "X-Nfse-Token": apiToken } }
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(
        typeof body.detail === "string" ? body.detail : "Não foi possível gerar o ZIP."
      );
    }
    await writeFile(job.destination, Buffer.from(await response.arrayBuffer()));
    await showDesktopNotification(
      "ZIP de notas concluído",
      `${job.companyName}: arquivo salvo em ${job.destination}`
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Falha desconhecida.";
    await showDesktopNotification("Falha ao gerar ZIP", `${job.companyName}: ${message}`);
  }
}

async function addSyncLog(
  cnpj: string,
  level: "info" | "warning" | "error",
  message: string
): Promise<void> {
  await api(`/companies/${cnpj}/sync/logs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ level, message })
  });
}

async function synchronizeWindowsCompany(company: CompanyRecord): Promise<void> {
  if (!company.certificate_reference) {
    throw new Error("Thumbprint do certificado do Windows nao encontrado.");
  }

  let requestedNsu = Math.max(0, Number(company.last_nsu || 0) - 50);
  let downloaded = 0;
  let networkAttempt = 0;
  const retryDelays = [15, 30, 60, 120, 300];

  while (true) {
    let stdout: string;
    try {
      const result = await execFileAsync(
        windowsHelperPath(),
        ["fetch", company.certificate_reference, String(requestedNsu)],
        {
          windowsHide: true,
          maxBuffer: 50 * 1024 * 1024,
          encoding: "utf8",
          env: { ...process.env, DOTNET_CLI_UI_LANGUAGE: "pt-BR" }
        }
      );
      stdout = result.stdout;
    } catch (error) {
      const detail = error as Error & { stderr?: string };
      const errorMessage = detail.stderr?.trim() || detail.message;
      if (errorMessage.toLocaleLowerCase("pt-BR").includes("certificado nao encontrado")) {
        await addSyncLog(company.cnpj, "error", errorMessage);
        throw new Error(errorMessage);
      }

      const delaySeconds = retryDelays[Math.min(networkAttempt, retryDelays.length - 1)];
      networkAttempt += 1;
      await addSyncLog(
        company.cnpj,
        "warning",
        `Falha de rede: ${errorMessage}. Nova tentativa em ${delaySeconds}s.`
      );
      await wait(delaySeconds * 1000);
      continue;
    }

    networkAttempt = 0;
    let response: Record<string, unknown>;
    try {
      response = JSON.parse(stdout) as Record<string, unknown>;
    } catch {
      throw new Error("O ADN retornou uma resposta invalida para o certificado do Windows.");
    }

    const batch = await api<{
      ok: boolean;
      continue: boolean;
      last_nsu: number;
      downloaded: number;
      diagnostic: string;
    }>(`/companies/${company.cnpj}/sync/windows/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requested_nsu: requestedNsu, response })
    });
    downloaded += batch.downloaded;
    if (!batch.ok) throw new Error(batch.diagnostic);
    if (!batch.continue) {
      await showSyncNotification(company.legal_name, downloaded);
      return;
    }
    requestedNsu = batch.last_nsu;
    await wait(5000);
  }
}

async function synchronizePfxCompany(
  company: CompanyRecord,
  password?: string
): Promise<void> {
  let credential = await readCredential(company.cnpj);
  if (!credential) {
    if (!password) throw new Error("Informe a senha do certificado.");
    const selection = await dialog.showOpenDialog({
      title: "Selecionar certificado para esta consulta",
      properties: ["openFile"],
      filters: [{ name: "Certificado A1", extensions: ["pfx", "p12"] }]
    });
    if (selection.canceled || selection.filePaths.length === 0) return;
    credential = {
      password,
      pfx: await readFile(selection.filePaths[0])
    };
  }

  const form = new FormData();
  form.set("certificate", new Blob([Uint8Array.from(credential.pfx)]), "certificate.pfx");
  form.set("password", credential.password);
  const result = await api<{
    ok: boolean;
    diagnostic: string;
    downloaded: number;
  }>(`/companies/${company.cnpj}/sync/pfx`, { method: "POST", body: form });
  if (!result.ok) throw new Error(result.diagnostic);
  await showSyncNotification(company.legal_name, result.downloaded);
}

async function synchronizeCompany(request: SyncRequest): Promise<void> {
  try {
    const companies = await api<CompanyRecord[]>("/companies");
    const company = companies.find((item) => item.cnpj === request.cnpj);
    if (!company) throw new Error("Empresa nao encontrada.");

    if (company.certificate_source === "windows") {
      await synchronizeWindowsCompany(company);
    } else {
      await synchronizePfxCompany(company, request.password);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Falha desconhecida.";
    await showDesktopNotification(
      "Sincronizacao temporariamente indisponivel",
      `${request.cnpj}: ${message}`
    );
  }
}

const exportQueue = new SequentialTaskQueue<ExportJob>(
  processExportJob,
  broadcastExportQueue,
  (job) => job.cnpj
);

function broadcastSyncQueue(snapshot: QueueSnapshot): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("sync:status", snapshot);
  }
}

const syncQueue = new SequentialTaskQueue<SyncRequest>(
  synchronizeCompany,
  broadcastSyncQueue,
  (request) => request.cnpj
);

function windowsHelperPath(): string {
  return app.isPackaged
    ? path.join(process.resourcesPath, "windows-cert-helper.exe")
    : path.join(projectRoot(), "windows-cert-helper", "bin", "Debug", "net10.0-windows",
      "Nfse.WindowsCertificates.exe");
}

function registerIpc(): void {
  ipcMain.handle("exports:status", () => exportQueue.snapshot());
  ipcMain.handle("sync:status", () => syncQueue.snapshot());
  ipcMain.handle("settings:get", () => api("/settings"));
  ipcMain.handle("settings:update", (_event, settings) =>
    api("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings)
    })
  );
  ipcMain.handle("settings:select-directory", async () => {
    const result = await dialog.showOpenDialog({
      title: "Selecionar pasta das notas",
      properties: ["openDirectory", "createDirectory"]
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle("window:minimize", () => mainWindow?.minimize());
  ipcMain.handle("window:toggle-maximize", () => {
    if (!mainWindow) return;
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  });
  ipcMain.handle("window:close", () => mainWindow?.hide());
  ipcMain.handle("companies:list", () => api("/companies"));
  ipcMain.handle("documents:list", (_event, input) => {
    lastDocumentQueryByCompany.set(input.cnpj, {
      startDate: input.startDate || input.data_inicial,
      endDate: input.endDate || input.data_final,
      direction: input.direction || input.tipo
    });
    const query = new URLSearchParams({
      page: String(input.page),
      per_page: String(input.perPage)
    });
    if (input.startDate) query.set("data_inicial", input.startDate);
    if (input.endDate) query.set("data_final", input.endDate);
    if (input.direction) query.set("tipo", input.direction);
    if (input.search) query.set("busca", input.search);
    if (input.status && input.status !== "todas") query.set("situacao", input.status);
    return api(`/companies/${input.cnpj}/documents?${query.toString()}`);
  });
  ipcMain.handle("documents:download", async (
    _event,
    cnpjOrInput: string | LegacyDownloadQuery,
    receivedStartDate?: string,
    receivedEndDate?: string,
    receivedDirection?: NoteDirection
  ) => {
    const requestedCnpj =
      typeof cnpjOrInput === "string" ? cnpjOrInput : cnpjOrInput.cnpj;
    const { cnpj, startDate, endDate, direction } = resolveDownloadQuery(
      cnpjOrInput,
      receivedStartDate,
      receivedEndDate,
      receivedDirection,
      lastDocumentQueryByCompany.get(requestedCnpj)
    );
    const filename =
      `${cnpj}-${direction}s-${startDate}-${endDate}.zip`;
    const destination = await dialog.showSaveDialog({
      title: "Salvar notas em ZIP",
      defaultPath: path.join(app.getPath("downloads"), filename),
      filters: [{ name: "Arquivo ZIP", extensions: ["zip"] }]
    });
    if (destination.canceled || !destination.filePath) return null;
    const companies = await api<Array<{ cnpj: string; legal_name: string }>>("/companies");
    const companyName =
      companies.find((company) => company.cnpj === cnpj)?.legal_name ?? cnpj;
    const position = exportQueue.enqueue({
      cnpj,
      companyName,
      startDate,
      endDate,
      direction,
      destination: destination.filePath
    });
    return { filePath: destination.filePath, position };
  });
  ipcMain.handle("sync:logs", (_event, cnpj: string) =>
    api(`/companies/${cnpj}/sync/logs?limit=20`)
  );
  ipcMain.handle("companies:register-pfx", async (_event, input) => {
    const selection = await dialog.showOpenDialog({
      title: "Selecionar certificado A1",
      properties: ["openFile"],
      filters: [{ name: "Certificado A1", extensions: ["pfx", "p12"] }]
    });
    if (selection.canceled || selection.filePaths.length === 0) return null;

    const pfx = await readFile(selection.filePaths[0]);
    const form = new FormData();
    form.set(
      "certificate",
      new Blob([Uint8Array.from(pfx)]),
      path.basename(selection.filePaths[0])
    );
    form.set("password", input.password);
    form.set("remember_certificate", String(input.remember));
    const company = await api<{ cnpj: string }>("/companies/pfx", {
      method: "POST",
      body: form
    });
    if (input.remember) {
      const reference = await saveCredential(company.cnpj, input.password, pfx);
      const updateForm = new FormData();
      updateForm.set(
        "certificate",
        new Blob([Uint8Array.from(pfx)]),
        path.basename(selection.filePaths[0])
      );
      updateForm.set("password", input.password);
      updateForm.set("remember_certificate", "true");
      updateForm.set("credential_reference", reference);
      return api("/companies/pfx", { method: "POST", body: updateForm });
    }
    await removeCredential(company.cnpj);
    return company;
  });
  ipcMain.handle("certificates:list-windows", listWindowsCertificates);
  ipcMain.handle("companies:register-windows", (_event, certificate: WindowsCertificate) =>
    api("/companies/windows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(certificate)
    })
  );
  ipcMain.handle("companies:sync", (_event, input: SyncRequest) => {
    const snapshot = syncQueue.snapshot();
    if (snapshot.activeId === input.cnpj || snapshot.pendingIds.includes(input.cnpj)) {
      return { position: 0, alreadyQueued: true };
    }
    const position = syncQueue.enqueue(input);
    return { position, alreadyQueued: false };
  });
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 980,
    minHeight: 640,
    backgroundColor: "#f4f6f5",
    title: "Gestor NFS-e",
    show: false,
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  mainWindow.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    mainWindow?.hide();
  });
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  const developmentUrl = process.env.VITE_DEV_SERVER_URL;
  if (developmentUrl) {
    await mainWindow.loadURL(developmentUrl);
  } else {
    await mainWindow.loadFile(path.join(app.getAppPath(), "dist", "index.html"));
  }
}

async function createTray(): Promise<void> {
  const icon = await app.getFileIcon(process.execPath, { size: "small" });
  tray = new Tray(icon);
  tray.setToolTip("Gestor NFS-e");
  tray.setContextMenu(Menu.buildFromTemplate([
    {
      label: "Abrir Gestor NFS-e",
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      }
    },
    { type: "separator" },
    {
      label: "Sair",
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]));
  tray.on("double-click", () => {
    mainWindow?.show();
    mainWindow?.focus();
  });
}

app.whenReady()
  .then(async () => {
    app.setAppUserModelId("br.com.gestornfse.app");
    Menu.setApplicationMenu(null);
    await startBackend();
    registerIpc();
    await createWindow();
    await createTray();
  })
  .catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    dialog.showErrorBox(
      "Gestor NFS-e não iniciou",
      `O serviço local não pôde ser iniciado.\n\n${message}`
    );
    isQuitting = true;
    app.quit();
  });

app.on("window-all-closed", () => {
  // A aplicacao continua disponivel na bandeja.
});

app.on("before-quit", () => {
  isQuitting = true;
  backendProcess?.kill();
});
