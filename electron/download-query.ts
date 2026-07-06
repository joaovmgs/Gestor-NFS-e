export type NoteDirection = "emitida" | "recebida";

export interface AppliedDownloadQuery {
  startDate?: string;
  endDate?: string;
  direction?: NoteDirection;
}

export interface LegacyDownloadQuery extends AppliedDownloadQuery {
  cnpj: string;
  data_inicial?: string;
  data_final?: string;
  tipo?: NoteDirection;
}

export interface ResolvedDownloadQuery {
  cnpj: string;
  startDate: string;
  endDate: string;
  direction: NoteDirection;
}

export function resolveDownloadQuery(
  cnpjOrInput: string | LegacyDownloadQuery,
  receivedStartDate?: string,
  receivedEndDate?: string,
  receivedDirection?: NoteDirection,
  appliedQuery?: AppliedDownloadQuery
): ResolvedDownloadQuery {
  const currentRange = currentMonthRange();
  const legacyInput = typeof cnpjOrInput === "object" ? cnpjOrInput : undefined;
  const cnpj = typeof cnpjOrInput === "string" ? cnpjOrInput : cnpjOrInput.cnpj;
  const startDate =
    legacyInput?.startDate ||
    legacyInput?.data_inicial ||
    receivedStartDate ||
    appliedQuery?.startDate ||
    currentRange.startDate;
  const endDate =
    legacyInput?.endDate ||
    legacyInput?.data_final ||
    receivedEndDate ||
    appliedQuery?.endDate ||
    currentRange.endDate;
  const requestedDirection =
    legacyInput?.direction ||
    legacyInput?.tipo ||
    receivedDirection ||
    appliedQuery?.direction;
  const direction =
    requestedDirection === "recebida" ? "recebida" : "emitida";
  return { cnpj, startDate, endDate, direction };
}

function currentMonthRange(): { startDate: string; endDate: string } {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const lastDay = String(new Date(year, now.getMonth() + 1, 0).getDate()).padStart(2, "0");
  return {
    startDate: `${year}-${month}-01`,
    endDate: `${year}-${month}-${lastDay}`
  };
}
