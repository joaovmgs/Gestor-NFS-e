import { contextBridge, ipcRenderer } from "electron";

async function invokeClean<T>(channel: string, ...args: unknown[]): Promise<T> {
  try {
    return await ipcRenderer.invoke(channel, ...args);
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    throw new Error(
      raw
        .replace(/^Error invoking remote method '[^']+':\s*/u, "")
        .replace(/^Error:\s*/u, "")
    );
  }
}

contextBridge.exposeInMainWorld("nfse", {
  listCompanies: () => invokeClean("companies:list"),
  registerPfxCompany: (input: {
    password: string;
    remember: boolean;
    queryCnpj?: string;
    queryCnpjs?: string[];
    allowPartial?: boolean;
  }) => invokeClean("companies:register-pfx", input),
  listWindowsCertificates: () => invokeClean("certificates:list-windows"),
  registerWindowsCompany: (
    certificate: WindowsCertificate,
    queryCnpj?: string,
    allowPartial = false
  ) => invokeClean("companies:register-windows", { certificate, queryCnpj, allowPartial }),
  deleteCompany: (cnpj: string) => invokeClean("companies:delete", cnpj),
  listDocuments: (input: DocumentQuery) => invokeClean("documents:list", input),
  downloadDocuments: (input: DownloadQuery) =>
    invokeClean(
      "documents:download",
      input.cnpj,
      input.startDate,
      input.endDate,
      input.direction
    ),
  getExportQueueStatus: () => invokeClean("exports:status"),
  onExportQueueStatus: (callback: (status: ExportQueueStatus) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: ExportQueueStatus) =>
      callback(status);
    ipcRenderer.on("exports:status", listener);
    return () => ipcRenderer.removeListener("exports:status", listener);
  },
  getSyncQueueStatus: () => invokeClean("sync:status"),
  onSyncQueueStatus: (callback: (status: ExportQueueStatus) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: ExportQueueStatus) =>
      callback(status);
    ipcRenderer.on("sync:status", listener);
    return () => ipcRenderer.removeListener("sync:status", listener);
  },
  listSyncLogs: (cnpj: string) => invokeClean("sync:logs", cnpj),
  syncCompany: (cnpj: string, password?: string, notify = true) =>
    invokeClean("companies:sync", { cnpj, password, notify }),
  getSettings: () => invokeClean("settings:get"),
  updateSettings: (settings: AppSettings) => invokeClean("settings:update", settings),
  selectNotesDirectory: () => invokeClean("settings:select-directory"),
  minimizeWindow: () => invokeClean("window:minimize"),
  toggleMaximizeWindow: () => invokeClean("window:toggle-maximize"),
  closeWindow: () => invokeClean("window:close")
});

interface WindowsCertificate {
  thumbprint: string;
  cnpj: string;
  legalName: string;
  expiresAt: string;
  issuer: string;
}

interface DocumentQuery {
  cnpj: string;
  startDate?: string;
  endDate?: string;
  direction?: "emitida" | "recebida";
  search?: string;
  status?: "todas" | "autorizada" | "cancelada";
  page: number;
  perPage: number;
}

interface DownloadQuery {
  cnpj: string;
  startDate: string;
  endDate: string;
  direction: "emitida" | "recebida";
}

interface ExportQueueStatus {
  processing: boolean;
  pending: number;
  activeId?: string;
  pendingIds: string[];
}

interface AppSettings {
  notes_directory: string;
  notifications_enabled: boolean;
}
