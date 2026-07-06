import {
  Building2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileKey2,
  FileText,
  FolderOpen,
  HardDrive,
  History,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import type {
  AppSettings,
  Company,
  Document,
  ExportQueueStatus,
  SyncLog,
  WindowsCertificate
} from "./types";

type Dialog = "method" | "pfx" | "windows" | "sync" | "settings" | null;

const formatCnpj = (value: string) =>
  value.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");

const formatMoney = (value?: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value ?? 0);

const formatDate = (value?: string) =>
  value ? new Intl.DateTimeFormat("pt-BR").format(new Date(value)) : "-";

const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium"
  }).format(new Date(`${value.replace(" ", "T")}Z`));

const syncStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    idle: "Pronto para consultar",
    syncing: "Sincronizando",
    waiting: "Aguardando nova tentativa",
    error: "Erro na sincronização"
  };
  return labels[status] ?? status;
};

const currentMonthRange = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const lastDay = new Date(year, now.getMonth() + 1, 0).getDate();
  return {
    start: `${year}-${month}-01`,
    end: `${year}-${month}-${String(lastDay).padStart(2, "0")}`
  };
};

export function App() {
  const initialRange = useMemo(currentMonthRange, []);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCnpj, setSelectedCnpj] = useState("");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentTotal, setDocumentTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [startDate, setStartDate] = useState(initialRange.start);
  const [endDate, setEndDate] = useState(initialRange.end);
  const [direction, setDirection] = useState<"emitida" | "recebida">("emitida");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [password, setPassword] = useState("");
  const [syncPassword, setSyncPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [windowsCertificates, setWindowsCertificates] = useState<WindowsCertificate[]>([]);
  const [search, setSearch] = useState("");
  const [documentStatus, setDocumentStatus] =
    useState<"todas" | "autorizada" | "cancelada">("todas");
  const [companySearch, setCompanySearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [exportQueue, setExportQueue] = useState<ExportQueueStatus>({
    processing: false,
    pending: 0,
    pendingIds: []
  });
  const [syncQueue, setSyncQueue] = useState<ExportQueueStatus>({
    processing: false,
    pending: 0,
    pendingIds: []
  });
  const [showSyncLogs, setShowSyncLogs] = useState(false);
  const [syncLogs, setSyncLogs] = useState<SyncLog[]>([]);
  const [settings, setSettings] = useState<AppSettings>({
    notes_directory: "",
    notifications_enabled: true
  });
  const [message, setMessage] = useState("");

  const selected = companies.find((company) => company.cnpj === selectedCnpj);
  const visibleCompanies = useMemo(() => {
    const query = companySearch.trim().toLocaleLowerCase("pt-BR");
    return [...companies]
      .sort((left, right) =>
        left.legal_name.localeCompare(right.legal_name, "pt-BR", { sensitivity: "base" })
      )
      .filter((company) => {
        if (!query) return true;
        return `${company.legal_name} ${company.cnpj}`
          .toLocaleLowerCase("pt-BR")
          .includes(query);
      });
  }, [companies, companySearch]);
  async function loadDocuments(
    cnpj: string,
    targetPage = 1,
    targetDirection: "emitida" | "recebida" = direction
  ) {
    const result = await window.nfse.listDocuments({
      cnpj,
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      direction: targetDirection,
      search: search.trim() || undefined,
      status: documentStatus,
      page: targetPage,
      perPage: 20
    });
    setDocuments(result.items);
    setDocumentTotal(result.total);
    setPage(result.page);
    setPages(result.pages);
  }

  async function loadCompanies(preferredCnpj?: string) {
    const result = await window.nfse.listCompanies();
    setCompanies(result);
    const next = preferredCnpj || selectedCnpj || result[0]?.cnpj || "";
    setSelectedCnpj(next);
    if (next) {
      await loadDocuments(next);
      const company = result.find((item) => item.cnpj === next);
      if (company?.remember_certificate || company?.certificate_source === "windows") {
        await window.nfse.syncCompany(next).catch(() => undefined);
      }
    }
    setLoading(false);
  }

  useEffect(() => {
    loadCompanies().catch((error) => {
      setMessage(error.message);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    window.nfse.getExportQueueStatus().then(setExportQueue).catch(() => undefined);
    return window.nfse.onExportQueueStatus(setExportQueue);
  }, []);

  useEffect(() => {
    window.nfse.getSyncQueueStatus().then(setSyncQueue).catch(() => undefined);
    return window.nfse.onSyncQueueStatus(setSyncQueue);
  }, []);

  useEffect(() => {
    if (!selectedCnpj) return;
    const timer = window.setTimeout(() => {
      loadDocuments(selectedCnpj, 1).catch(() => undefined);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search, documentStatus]);

  useEffect(() => {
    const selectedIsSyncing =
      syncQueue.activeId === selectedCnpj || syncQueue.pendingIds.includes(selectedCnpj);
    if (!selectedCnpj || (!showSyncLogs && !selectedIsSyncing)) return;
    const refresh = () => {
      window.nfse.listSyncLogs(selectedCnpj).then(setSyncLogs).catch(() => undefined);
      if (selectedIsSyncing) {
        window.nfse.listCompanies().then(setCompanies).catch(() => undefined);
        loadDocuments(selectedCnpj, page).catch(() => undefined);
      }
    };
    refresh();
    if (!selectedIsSyncing) return;
    const interval = window.setInterval(refresh, 3000);
    return () => window.clearInterval(interval);
  }, [selectedCnpj, showSyncLogs, syncQueue]);

  async function selectCompany(cnpj: string) {
    setSelectedCnpj(cnpj);
    setShowSyncLogs(false);
    setSyncLogs([]);
    await loadDocuments(cnpj);
    const company = companies.find((item) => item.cnpj === cnpj);
    if (company?.remember_certificate || company?.certificate_source === "windows") {
      await window.nfse.syncCompany(cnpj).catch(() => undefined);
    }
  }

  async function registerPfx(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      const company = await window.nfse.registerPfxCompany({ password, remember });
      if (!company) return;
      setDialog(null);
      setPassword("");
      await loadCompanies(company.cnpj);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Nao foi possivel cadastrar.");
    }
  }

  async function openWindowsCertificates() {
    setDialog("windows");
    setMessage("");
    try {
      setWindowsCertificates(await window.nfse.listWindowsCertificates());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao consultar certificados.");
    }
  }

  async function openSettings() {
    setMessage("");
    try {
      setSettings(await window.nfse.getSettings());
      setDialog("settings");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao carregar configurações.");
    }
  }

  async function chooseNotesDirectory() {
    const selectedDirectory = await window.nfse.selectNotesDirectory();
    if (selectedDirectory) {
      setSettings((current) => ({ ...current, notes_directory: selectedDirectory }));
    }
  }

  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    try {
      setSettings(await window.nfse.updateSettings(settings));
      setDialog(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao salvar configurações.");
    }
  }

  async function registerWindows(certificate: WindowsCertificate) {
    setMessage("");
    try {
      const company = await window.nfse.registerWindowsCompany(certificate);
      setDialog(null);
      await loadCompanies(company.cnpj);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao cadastrar certificado.");
    }
  }

  async function syncCompany(passwordForSession?: string) {
    if (!selected) return;
    setMessage("");
    try {
      const queued = await window.nfse.syncCompany(selected.cnpj, passwordForSession);
      setDialog(null);
      setSyncPassword("");
      setMessage(
        queued.alreadyQueued
          ? "Esta empresa já está na fila de sincronização."
          : queued.position === 1
            ? "Sincronização iniciada."
            : `Empresa adicionada à fila de sincronização na posição ${queued.position}.`
      );
    } catch (error) {
      setMessage(
        "Não foi possível concluir a sincronização agora. " +
        "O Gestor NFS-e aguardará antes de consultar novamente quando o Portal Nacional estiver disponível."
      );
      await loadCompanies(selected.cnpj).catch(() => undefined);
      setSyncLogs(await window.nfse.listSyncLogs(selected.cnpj).catch(() => []));
      setShowSyncLogs(true);
    }
  }

  async function changeDirection(nextDirection: "emitida" | "recebida") {
    if (!selected || nextDirection === direction) return;
    setDirection(nextDirection);
    setSearch("");
    await loadDocuments(selected.cnpj, 1, nextDirection);
  }

  async function downloadDocuments() {
    if (!selected) return;
    setMessage("");
    setDownloading(true);
    try {
      const queuedExport = await window.nfse.downloadDocuments({
        cnpj: selected.cnpj,
        startDate,
        endDate,
        direction
      });
      if (queuedExport) {
        setMessage(
          queuedExport.position === 1
            ? "Exportação iniciada. Você pode continuar usando o aplicativo."
            : `Exportação adicionada à fila na posição ${queuedExport.position}.`
        );
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível gerar o ZIP.");
    } finally {
      setDownloading(false);
    }
  }

  const selectedExportActive = Boolean(
    selected && exportQueue.activeId === selected.cnpj
  );
  const selectedExportPending = selected
    ? exportQueue.pendingIds.filter((cnpj) => cnpj === selected.cnpj).length
    : 0;
  const selectedSyncActive = Boolean(selected && syncQueue.activeId === selected.cnpj);
  const selectedSyncPending = selected
    ? syncQueue.pendingIds.filter((cnpj) => cnpj === selected.cnpj).length
    : 0;

  return (
    <div className="app-shell">
      <div className="window-titlebar">
        <span>Gestor NFS-e</span>
        <div className="window-controls">
          <button className="window-dot green" title="Maximizar ou restaurar" onClick={() => window.nfse.toggleMaximizeWindow()} />
          <button className="window-dot yellow" title="Minimizar" onClick={() => window.nfse.minimizeWindow()} />
          <button className="window-dot red" title="Fechar para a bandeja" onClick={() => window.nfse.closeWindow()} />
        </div>
      </div>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><FileText size={20} /></div>
          <div><strong>Gestor NFS-e</strong><span>Portal Nacional</span></div>
        </div>

        <div className="sidebar-heading">
          <span>Empresas</span>
          <button className="icon-button" title="Cadastrar empresa" onClick={() => setDialog("method")}>
            <Plus size={17} />
          </button>
        </div>
        <div className="company-search">
          <Search size={15} />
          <input
            value={companySearch}
            onChange={(event) => setCompanySearch(event.target.value)}
            placeholder="Pesquisar empresa"
            aria-label="Pesquisar empresas"
          />
        </div>
        <nav className="company-list" aria-label="Empresas cadastradas">
          {visibleCompanies.map((company) => (
            <button
              className={`company-item ${company.cnpj === selectedCnpj ? "active" : ""}`}
              key={company.cnpj}
              onClick={() => selectCompany(company.cnpj)}
            >
              <span className="company-icon"><Building2 size={17} /></span>
              <span className="company-copy">
                <strong>{company.legal_name}</strong>
                <small>{formatCnpj(company.cnpj)}</small>
              </span>
              <ChevronRight size={15} />
            </button>
          ))}
          {!loading && companies.length === 0 && (
            <div className="empty-sidebar">Nenhuma empresa cadastrada.</div>
          )}
          {!loading && companies.length > 0 && visibleCompanies.length === 0 && (
            <div className="empty-sidebar">Nenhuma empresa encontrada.</div>
          )}
        </nav>
        <div className="sidebar-footer">
          <button className="settings-button" onClick={openSettings}><Settings size={16} /> Configurações</button>
          <div className="local-status"><ShieldCheck size={15} /> Dados somente neste computador</div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>{selected?.legal_name ?? "Empresas"}</h1>
            <p>{selected ? formatCnpj(selected.cnpj) : "Cadastre uma empresa para iniciar"}</p>
          </div>
        </header>

        {message && <div className="notice">{message}<button onClick={() => setMessage("")}><X size={15} /></button></div>}

        {!selected ? (
          <section className="welcome">
            <div className="welcome-icon"><FileKey2 size={30} /></div>
            <h2>Nenhuma empresa cadastrada</h2>
            <p>Os dados das empresas aparecerão neste espaço.</p>
          </section>
        ) : (
          <>
            <section className="summary-band">
              <div><span>Último NSU</span><strong>{selected.last_nsu}</strong></div>
              <div><span>Documentos no período</span><strong>{documentTotal}</strong></div>
              <div><span>Certificado válido até</span><strong>{formatDate(selected.certificate_expires_at)}</strong></div>
              <div className="sync-box">
                <span className={`status-dot ${selected.sync_status}`} />
                <span>{syncStatusLabel(selected.sync_status)}</span>
                <button className="button sync" disabled={selectedSyncActive || selectedSyncPending > 0} onClick={() => selected.remember_certificate ? syncCompany() : setDialog("sync")}>
                  <RefreshCw className={selectedSyncActive ? "spinning" : ""} size={16} /> {selectedSyncActive ? "Sincronizando" : selectedSyncPending ? "Na fila" : "Sincronizar"}
                </button>
              </div>
            </section>
            <section className={`sync-log-panel ${showSyncLogs ? "open" : ""}`}>
              <button className="sync-log-toggle" onClick={() => setShowSyncLogs((current) => !current)}>
                <History size={15} />
                <span>
                  <strong>Detalhes da sincronização</strong>
                  <small>{selected.diagnostic || "Nenhuma consulta registrada."}</small>
                </span>
                <ChevronRight className={showSyncLogs ? "rotated" : ""} size={16} />
              </button>
              {showSyncLogs && (
                <div className="sync-log-list">
                  {syncLogs.map((log) => (
                    <div className={`sync-log-entry ${log.level}`} key={log.id}>
                      <time>{formatDateTime(log.created_at)}</time>
                      <span>{log.message}</span>
                    </div>
                  ))}
                  {syncLogs.length === 0 && <div className="empty-log">Nenhum evento de sincronização.</div>}
                </div>
              )}
            </section>

            <section className="documents">
              <div className="documents-heading">
                <div><h2>Notas fiscais</h2><p>Documentos armazenados neste computador</p></div>
                <div className="document-tabs" role="tablist" aria-label="Tipo de nota">
                  <button role="tab" aria-selected={direction === "emitida"} className={direction === "emitida" ? "active" : ""} onClick={() => changeDirection("emitida")}>Emitidas</button>
                  <button role="tab" aria-selected={direction === "recebida"} className={direction === "recebida" ? "active" : ""} onClick={() => changeDirection("recebida")}>Recebidas</button>
                </div>
              </div>
              <div className="filter-bar">
                <div className="period-fields">
                  <label className="date-filter">Data inicial<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
                  <label className="date-filter">Data final<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
                  <button className="button secondary filter-button" onClick={() => loadDocuments(selected.cnpj, 1)}>Aplicar período</button>
                  <button className="button primary filter-button" disabled={downloading} onClick={downloadDocuments}>
                    <Download size={16} /> {downloading ? "Gerando ZIP" : "Baixar ZIP"}
                  </button>
                </div>
                <div className="document-query">
                  <select value={documentStatus} onChange={(event) => setDocumentStatus(event.target.value as typeof documentStatus)} aria-label="Filtrar por situação">
                    <option value="todas">Todas as situações</option>
                    <option value="autorizada">Autorizadas</option>
                    <option value="cancelada">Canceladas</option>
                  </select>
                  <div className="search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Número, prestador, tomador ou valor" /></div>
                </div>
              </div>
              {(downloading || selectedExportActive || selectedExportPending > 0) && (
                <div className="export-progress" role="status" aria-live="polite">
                  <RefreshCw className="spinning" size={15} />
                  <span>
                    {downloading
                      ? "Preparando a exportação..."
                      : selectedExportActive
                        ? "Gerando ZIP desta empresa com os arquivos XML e PDF."
                        : `${selectedExportPending} exportação(ões) desta empresa aguardando na fila.`}
                  </span>
                </div>
              )}
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Número da nota</th><th>Emissão</th><th>Prestador</th><th>Tomador</th><th>Valor</th><th>Situação</th></tr></thead>
                  <tbody>
                    {documents.map((document) => (
                      <tr key={document.id}>
                        <td className="mono">{document.note_number || "-"}</td>
                        <td>{formatDate(document.issued_at)}</td>
                        <td>{document.issuer_name || "-"}</td>
                        <td>{document.customer_name || "-"}</td>
                        <td className="money">{formatMoney(document.service_amount)}</td>
                        <td><span className="status-badge">{document.status || "Autorizada"}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {documents.length === 0 && <div className="empty-table">Nenhuma nota encontrada com os filtros informados.</div>}
              </div>
              <div className="pagination">
                <span>{documentTotal === 0 ? "Nenhum documento" : `Página ${page} de ${pages} · ${documentTotal} documentos`}</span>
                <div>
                  <button className="icon-button" title="Página anterior" disabled={page <= 1} onClick={() => loadDocuments(selected.cnpj, page - 1)}><ChevronLeft size={17} /></button>
                  <button className="icon-button" title="Próxima página" disabled={page >= pages} onClick={() => loadDocuments(selected.cnpj, page + 1)}><ChevronRight size={17} /></button>
                </div>
              </div>
            </section>
          </>
        )}
      </main>

      {dialog === "method" && (
        <div className="dialog-backdrop">
          <div className="dialog">
            <div className="dialog-header"><div><h2>Cadastrar empresa</h2><p>Escolha onde está o certificado digital.</p></div><button className="icon-button" onClick={() => setDialog(null)}><X size={18} /></button></div>
            <div className="method-options">
              <button onClick={() => setDialog("pfx")}>
                <span className="method-icon"><FileKey2 size={22} /></span>
                <span><strong>Arquivo PFX ou P12</strong><small>Selecionar um certificado salvo neste computador.</small></span>
                <ChevronRight size={17} />
              </button>
              <button onClick={openWindowsCertificates}>
                <span className="method-icon"><HardDrive size={22} /></span>
                <span><strong>Instalado no Windows</strong><small>Usar um certificado do repositório pessoal.</small></span>
                <ChevronRight size={17} />
              </button>
            </div>
          </div>
        </div>
      )}

      {dialog === "pfx" && (
        <div className="dialog-backdrop" role="presentation">
          <form className="dialog" onSubmit={registerPfx}>
            <div className="dialog-header"><div><h2>Cadastrar com PFX</h2><p>Selecione o arquivo depois de confirmar.</p></div><button type="button" className="icon-button" onClick={() => setDialog(null)}><X size={18} /></button></div>
            <label>Senha do certificado<input type="password" required autoFocus value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <label className="check-row"><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} /><span><strong>Armazenar certificado e senha</strong><small>Protegidos pela credencial do Windows para consultas futuras.</small></span></label>
            {!remember && <div className="inline-info">As notas continuarão salvas, mas o arquivo e a senha serão solicitados em cada nova consulta.</div>}
            <div className="dialog-actions"><button type="button" className="button secondary" onClick={() => setDialog(null)}>Cancelar</button><button className="button primary"><FileKey2 size={17} /> Selecionar arquivo</button></div>
          </form>
        </div>
      )}

      {dialog === "windows" && (
        <div className="dialog-backdrop">
          <div className="dialog wide">
            <div className="dialog-header"><div><h2>Certificados do Windows</h2><p>Repositório Pessoal do usuário atual</p></div><button className="icon-button" onClick={() => setDialog(null)}><X size={18} /></button></div>
            <div className="certificate-list">
              {windowsCertificates.map((certificate) => (
                <button key={certificate.thumbprint} onClick={() => registerWindows(certificate)}>
                  <span className="certificate-icon"><ShieldCheck size={20} /></span>
                  <span><strong>{certificate.legalName}</strong><small>{formatCnpj(certificate.cnpj)} · válido até {formatDate(certificate.expiresAt)}</small><small>{certificate.issuer}</small></span>
                  <ChevronRight size={17} />
                </button>
              ))}
              {windowsCertificates.length === 0 && <div className="empty-table">Nenhum certificado A1 com chave privada e CNPJ foi localizado.</div>}
            </div>
          </div>
        </div>
      )}

      {dialog === "sync" && selected && (
        <div className="dialog-backdrop">
          <form className="dialog" onSubmit={(event) => { event.preventDefault(); syncCompany(syncPassword); }}>
            <div className="dialog-header"><div><h2>Consultar novas notas</h2><p>O certificado não foi armazenado para esta empresa.</p></div><button type="button" className="icon-button" onClick={() => setDialog(null)}><X size={18} /></button></div>
            <label>Senha do certificado<input type="password" required autoFocus value={syncPassword} onChange={(event) => setSyncPassword(event.target.value)} /></label>
            <div className="inline-info">Após confirmar, selecione novamente o arquivo PFX/P12. Ele será usado apenas nesta consulta.</div>
            <div className="dialog-actions"><button type="button" className="button secondary" onClick={() => setDialog(null)}>Cancelar</button><button className="button primary"><RefreshCw size={17} /> Selecionar e consultar</button></div>
          </form>
        </div>
      )}

      {dialog === "settings" && (
        <div className="dialog-backdrop">
          <form className="dialog wide" onSubmit={saveSettings}>
            <div className="dialog-header"><div><h2>Configurações</h2><p>Preferências locais do Gestor NFS-e</p></div><button type="button" className="icon-button" onClick={() => setDialog(null)}><X size={18} /></button></div>
            <div className="settings-form">
              <label className="settings-field">
                <span>Pasta das notas</span>
                <div className="directory-input">
                  <input value={settings.notes_directory} readOnly />
                  <button type="button" className="icon-button" title="Selecionar pasta" onClick={chooseNotesDirectory}><FolderOpen size={17} /></button>
                </div>
                <small>Novos XMLs serão organizados por CNPJ dentro desta pasta.</small>
              </label>
              <label className="check-row settings-check">
                <input type="checkbox" checked={settings.notifications_enabled} onChange={(event) => setSettings((current) => ({ ...current, notifications_enabled: event.target.checked }))} />
                <span><strong>Notificações do Windows</strong><small>Avisar quando uma sincronização for concluída.</small></span>
              </label>
            </div>
            <div className="dialog-actions"><button type="button" className="button secondary" onClick={() => setDialog(null)}>Cancelar</button><button className="button primary">Salvar configurações</button></div>
          </form>
        </div>
      )}
    </div>
  );
}
