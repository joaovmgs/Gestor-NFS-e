export interface WindowsCertificate {
  thumbprint: string;
  cnpj: string;
  legalName: string;
  expiresAt: string;
  issuer: string;
}

export function validateWindowsCertificate(certificate: WindowsCertificate): void {
  const cnpj = certificate.cnpj.replace(/\D/g, "");
  if (cnpj.length !== 14) {
    throw new Error("O certificado selecionado não possui um CNPJ válido.");
  }
  if (!certificate.thumbprint.replace(/[^0-9a-f]/gi, "")) {
    throw new Error("O certificado selecionado não possui identificador válido.");
  }
  const expiration = Date.parse(certificate.expiresAt);
  if (Number.isNaN(expiration)) {
    throw new Error("Não foi possível validar a data de vencimento do certificado.");
  }
  if (expiration < Date.now()) {
    throw new Error("O certificado digital está vencido.");
  }
}
