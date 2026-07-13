export interface Company {
  cnpj: string;
  legal_name: string;
  certificate_source: "pfx" | "windows";
  certificate_cnpj?: string;
  remember_certificate: number;
  certificate_reference?: string;
  certificate_expires_at: string;
  last_nsu: number;
  sync_status: string;
  diagnostic?: string;
}

export interface WindowsCertificate {
  thumbprint: string;
  cnpj: string;
  legalName: string;
  expiresAt: string;
  issuer: string;
}

export interface Document {
  id: number;
  nsu: number;
  note_number?: string;
  access_key: string;
  direction: string;
  issued_at?: string;
  issuer_name?: string;
  customer_name?: string;
  service_amount?: number;
  status: string;
}

export interface DocumentPage {
  items: Document[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface SyncLog {
  id: number;
  level: "info" | "warning" | "error";
  message: string;
  created_at: string;
}

export interface AppSettings {
  notes_directory: string;
  notifications_enabled: boolean;
  environment: "producao" | "producao_restrita";
}

export interface ExportQueueStatus {
  processing: boolean;
  pending: number;
  activeId?: string;
  pendingIds: string[];
}

export interface ExportQueueResult {
  filePath: string;
  position: number;
}

export interface SyncQueueResult {
  position: number;
  alreadyQueued: boolean;
}

export interface CompanyRegistrationResult {
  companies: Company[];
  valid_cnpjs: string[];
  invalid: Array<{ cnpj: string; message: string }>;
  has_invalid: boolean;
}

export interface NfseApi {
  listCompanies(): Promise<Company[]>;
  registerPfxCompany(input: {
    password: string;
    remember: boolean;
    queryCnpj?: string;
    queryCnpjs?: string[];
    allowPartial?: boolean;
  }): Promise<CompanyRegistrationResult | null>;
  listWindowsCertificates(): Promise<WindowsCertificate[]>;
  registerWindowsCompany(
    certificate: WindowsCertificate,
    queryCnpj?: string,
    allowPartial?: boolean
  ): Promise<CompanyRegistrationResult>;
  deleteCompany(cnpj: string): Promise<{ removed: boolean }>;
  listDocuments(input: {
    cnpj: string;
    startDate?: string;
    endDate?: string;
    direction?: "emitida" | "recebida";
    search?: string;
    status?: "todas" | "autorizada" | "cancelada";
    page: number;
    perPage: number;
  }): Promise<DocumentPage>;
  downloadDocuments(input: {
    cnpj: string;
    startDate: string;
    endDate: string;
    direction: "emitida" | "recebida";
  }): Promise<ExportQueueResult | null>;
  getExportQueueStatus(): Promise<ExportQueueStatus>;
  onExportQueueStatus(callback: (status: ExportQueueStatus) => void): () => void;
  getSyncQueueStatus(): Promise<ExportQueueStatus>;
  onSyncQueueStatus(callback: (status: ExportQueueStatus) => void): () => void;
  listSyncLogs(cnpj: string): Promise<SyncLog[]>;
  syncCompany(cnpj: string, password?: string, notify?: boolean): Promise<SyncQueueResult>;
  getSettings(): Promise<AppSettings>;
  updateSettings(settings: AppSettings): Promise<AppSettings>;
  selectNotesDirectory(): Promise<string | null>;
  minimizeWindow(): Promise<void>;
  toggleMaximizeWindow(): Promise<void>;
  closeWindow(): Promise<void>;
}

declare global {
  interface Window {
    nfse: NfseApi;
  }
}
