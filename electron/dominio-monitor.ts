import type { DominioResult } from "./dominio-config.js";

export interface DominioStatus {
  state: "disabled" | "checking" | "connected" | "offline";
  lastSuccess?: string;
  message: string;
  result?: DominioResult;
}

export class DominioMonitor {
  status: DominioStatus = { state: "disabled", message: "Integração Domínio desativada." };
  private pending?: Promise<void>;
  private checked = false;

  constructor(
    private readonly query: () => Promise<DominioResult | null>,
    private readonly now: () => number = Date.now,
  ) {}

  async wait(): Promise<void> { await this.pending; }

  async configure(task: () => Promise<DominioResult>): Promise<DominioResult> {
    await this.wait();
    const operation = task().then(result => {
      this.connected(result);
      return result;
    });
    this.pending = operation.then(() => undefined, () => undefined)
      .finally(() => { this.pending = undefined; });
    return operation;
  }

  connected(result: DominioResult): void {
    this.status = {
      state: "connected", lastSuccess: new Date(this.now()).toISOString(), result,
      message: result.issues.length
        ? `Domínio consultado · ${result.issues.length} empresa(s) com cadastro provisório.`
        : "Domínio consultado · cadastros atualizados.",
    };
    this.checked = true;
  }

  refresh(force = false): Promise<void> {
    if (this.pending) return this.pending;
    if (!force && this.checked) return Promise.resolve();
    this.pending = this.run().finally(() => { this.pending = undefined; });
    return this.pending;
  }

  private async run(): Promise<void> {
    this.status = { ...this.status, state: "checking", message: "Consultando o Domínio..." };
    try {
      const result = await this.query();
      if (result) this.connected(result);
      else this.status = { state: "disabled", message: "Integração Domínio desativada." };
    } catch {
      this.status = {
        ...this.status, state: "offline",
        message: "Domínio indisponível na última consulta. Usando vínculos salvos ou nomes provisórios. Consulte novamente nas configurações.",
      };
    } finally {
      this.checked = true;
    }
  }
}
