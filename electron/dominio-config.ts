export interface DominioConfig {
  driver: string;
  server: string;
  database: string;
  uid: string;
  pwd: string;
  host: string;
}

export interface DominioResult {
  matched: number;
  issues: Array<{ cnpj: string; message: string }>;
}
