export interface WindowsCertificate {
  thumbprint: string;
  cnpj: string;
  legalName: string;
  expiresAt: string;
  issuer: string;
}

export interface StoredCertificateMetadata {
  certificate_expires_at: string;
  certificate_status?: "valid" | "expired" | "invalid";
  certificate_message?: string;
}

export function validateStoredCertificate(certificate: StoredCertificateMetadata): void {
  if (certificate.certificate_status && certificate.certificate_status !== "valid") {
    throw new Error(
      certificate.certificate_message ||
        "Atualize o certificado desta empresa antes de sincronizar."
    );
  }
  validateCertificateExpiration(certificate.certificate_expires_at);
}

export function validateWindowsCertificate(certificate: WindowsCertificate): void {
  const cnpj = certificate.cnpj.replace(/[^0-9a-z]/gi, "");
  if (cnpj.length !== 14) {
    throw new Error("O certificado selecionado não possui um CNPJ válido.");
  }
  if (!certificate.thumbprint.replace(/[^0-9a-f]/gi, "")) {
    throw new Error("O certificado selecionado não possui identificador válido.");
  }
  validateCertificateExpiration(certificate.expiresAt);
}

function validateCertificateExpiration(expiresAt: string): void {
  const expiration = Date.parse(expiresAt);
  if (Number.isNaN(expiration)) {
    throw new Error("Não foi possível validar a data de vencimento do certificado.");
  }
  if (expiration < Date.now()) {
    throw new Error("O certificado digital está vencido.");
  }
}
