import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("nfse", {
  listCompanies: () => ipcRenderer.invoke("companies:list"),
  registerPfxCompany: (input: { password: string; remember: boolean }) =>
    ipcRenderer.invoke("companies:register-pfx", input),
  listWindowsCertificates: () => ipcRenderer.invoke("certificates:list-windows"),
  registerWindowsCompany: (certificate: WindowsCertificate) =>
    ipcRenderer.invoke("companies:register-windows", certificate),
  listDocuments: (input: DocumentQuery) => ipcRenderer.invoke("documents:list", input),
  downloadDocuments: (input: DownloadQuery) =>
    ipcRenderer.invoke(
      "documents:download",
      input.cnpj,
      input.startDate,
      input.endDate,
      input.direction
    ),
  getExportQueueStatus: () => ipcRenderer.invoke("exports:status"),
  onExportQueueStatus: (callback: (status: ExportQueueStatus) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: ExportQueueStatus) =>
      callback(status);
    ipcRenderer.on("exports:status", listener);
    return () => ipcRenderer.removeListener("exports:status", listener);
  },
  getSyncQueueStatus: () => ipcRenderer.invoke("sync:status"),
  onSyncQueueStatus: (callback: (status: ExportQueueStatus) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: ExportQueueStatus) =>
      callback(status);
    ipcRenderer.on("sync:status", listener);
    return () => ipcRenderer.removeListener("sync:status", listener);
  },
  listSyncLogs: (cnpj: string) => ipcRenderer.invoke("sync:logs", cnpj),
  syncCompany: (cnpj: string, password?: string) =>
    ipcRenderer.invoke("companies:sync", { cnpj, password }),
  getSettings: () => ipcRenderer.invoke("settings:get"),
  updateSettings: (settings: AppSettings) => ipcRenderer.invoke("settings:update", settings),
  selectNotesDirectory: () => ipcRenderer.invoke("settings:select-directory"),
  minimizeWindow: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximizeWindow: () => ipcRenderer.invoke("window:toggle-maximize"),
  closeWindow: () => ipcRenderer.invoke("window:close")
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
