import assert from "node:assert/strict";
import test from "node:test";

import {
  validateWindowsCertificate,
  WindowsCertificate
} from "./certificate-validation.js";

function certificate(overrides: Partial<WindowsCertificate> = {}): WindowsCertificate {
  return {
    thumbprint: "ABCDEF123456",
    cnpj: "12.345.678/0001-90",
    legalName: "EMPRESA TESTE",
    expiresAt: new Date(Date.now() + 86_400_000).toISOString(),
    issuer: "AC TESTE",
    ...overrides
  };
}

test("accepts a valid Windows certificate payload", () => {
  assert.doesNotThrow(() => validateWindowsCertificate(certificate()));
});

test("rejects a Windows certificate without a valid CNPJ", () => {
  assert.throws(
    () => validateWindowsCertificate(certificate({ cnpj: "123" })),
    /CNPJ valido|CNPJ válido/
  );
});

test("rejects a Windows certificate without a thumbprint", () => {
  assert.throws(
    () => validateWindowsCertificate(certificate({ thumbprint: "" })),
    /identificador valido|identificador válido/
  );
});

test("rejects a Windows certificate with an invalid expiration date", () => {
  assert.throws(
    () => validateWindowsCertificate(certificate({ expiresAt: "data-invalida" })),
    /data de vencimento/
  );
});

test("rejects an expired Windows certificate", () => {
  assert.throws(
    () => validateWindowsCertificate(certificate({
      expiresAt: new Date(Date.now() - 86_400_000).toISOString()
    })),
    /vencido/
  );
});
