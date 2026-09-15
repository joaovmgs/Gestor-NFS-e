from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID, ObjectIdentifier

CNPJ_OID = ObjectIdentifier("2.16.76.1.3.3")


@dataclass(frozen=True)
class CertificateInfo:
    cnpj: str
    legal_name: str
    expires_at: str
    issuer: str


@dataclass(frozen=True)
class CertificateHealth:
    status: str
    message: str


def evaluate_certificate_health(
    expires_at: object,
    *,
    certificate_source: object = "pfx",
    certificate_reference: object = None,
    sync_status: object = "idle",
    diagnostic: object = "",
    now: datetime | None = None,
) -> CertificateHealth:
    if str(certificate_source or "") == "windows" and not str(
        certificate_reference or ""
    ).strip():
        return CertificateHealth(
            "invalid",
            "O certificado não foi encontrado no repositório do Windows.",
        )

    expiration_text = str(expires_at or "").strip()
    if not expiration_text:
        return CertificateHealth(
            "invalid",
            "A data de validade do certificado não está disponível.",
        )
    try:
        expiration = _as_utc(datetime.fromisoformat(expiration_text.replace("Z", "+00:00")))
    except ValueError:
        return CertificateHealth(
            "invalid",
            "Não foi possível validar a data de vencimento do certificado.",
        )

    checked_at = _as_utc(now or datetime.now(UTC))
    if expiration < checked_at:
        return CertificateHealth(
            "expired",
            f"O certificado digital venceu em {expiration.astimezone(UTC):%d/%m/%Y}.",
        )

    normalized_diagnostic = _normalize_message(str(diagnostic or ""))
    if (
        str(sync_status or "") == "error"
        and "certificado" in normalized_diagnostic
        and "vencid" in normalized_diagnostic
    ):
        return CertificateHealth(
            "expired",
            str(diagnostic).strip() or "O certificado digital está vencido.",
        )
    certificate_error = "certificado" in normalized_diagnostic and any(
        fragment in normalized_diagnostic
        for fragment in (
            "corrompido",
            "invalido",
            "nao encontrado",
            "nao possui",
            "ainda nao esta valido",
            "chave privada",
            "cnpj",
        )
    )
    password_error = "senha incorreta" in normalized_diagnostic
    if str(sync_status or "") == "error" and (certificate_error or password_error):
        return CertificateHealth(
            "invalid",
            str(diagnostic).strip() or "Não foi possível usar o certificado digital.",
        )

    return CertificateHealth("valid", "")


def validate_certificate_period(not_before: datetime, not_after: datetime) -> None:
    now = datetime.now(UTC)
    start = _as_utc(not_before)
    end = _as_utc(not_after)
    if start > now:
        raise ValueError("O certificado ainda nao esta valido.")
    if end < now:
        raise ValueError("O certificado digital esta vencido.")


def validate_certificate_expiration(expires_at: str) -> None:
    try:
        expiration = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Data de validade do certificado invalida.") from exc
    validate_certificate_period(datetime.min.replace(tzinfo=UTC), expiration)


def normalize_cnpj(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value).upper()


def resolve_consulted_cnpj(certificate_cnpj: str, requested_cnpj: str | None = None) -> str:
    certificate_identifier = normalize_cnpj(certificate_cnpj)
    requested_identifier = normalize_cnpj(requested_cnpj or certificate_identifier)
    if len(certificate_identifier) != 14:
        raise ValueError("CNPJ do certificado invalido.")
    if len(requested_identifier) != 14:
        raise ValueError("CNPJ consultado invalido.")
    if certificate_identifier[:8] != requested_identifier[:8]:
        raise ValueError("O CNPJ consultado precisa ter a mesma raiz do CNPJ do certificado.")
    return requested_identifier


def inspect_pfx(content: bytes, password: str) -> CertificateInfo:
    try:
        private_key, certificate, _chain = pkcs12.load_key_and_certificates(
            content,
            password.encode("utf-8"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Senha incorreta ou certificado PFX/P12 invalido.") from exc

    if private_key is None or certificate is None:
        raise ValueError("O arquivo precisa conter certificado e chave privada.")

    validate_certificate_period(
        certificate.not_valid_before_utc,
        certificate.not_valid_after_utc,
    )

    cnpj = _cnpj_from_certificate(certificate)
    if not cnpj:
        raise ValueError("Nao foi possivel identificar o CNPJ no certificado.")

    common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    legal_name = common_names[0].value if common_names else cnpj
    expires_at = certificate.not_valid_after_utc.astimezone(UTC).isoformat()
    return CertificateInfo(
        cnpj=cnpj,
        legal_name=legal_name,
        expires_at=expires_at,
        issuer=certificate.issuer.rfc4514_string(),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_message(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _cnpj_from_certificate(certificate: x509.Certificate) -> str:
    try:
        extension = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for other_name in extension.value.get_values_for_type(x509.OtherName):
            if other_name.type_id == CNPJ_OID:
                identifier = normalize_cnpj(_decode_der_string(other_name.value))
                if len(identifier) == 14:
                    return identifier
    except x509.ExtensionNotFound:
        pass

    identifiers = re.findall(
        r"(?<![0-9A-Za-z])(?=[0-9A-Za-z]{14}(?![0-9A-Za-z]))"
        r"(?=[0-9A-Za-z]*\d)[0-9A-Za-z]{14}",
        certificate.subject.rfc4514_string(),
    )
    return identifiers[0].upper() if identifiers else ""


def _decode_der_string(value: bytes) -> str:
    if len(value) < 2:
        return ""
    length = value[1]
    offset = 2
    if length & 0x80:
        length_size = length & 0x7F
        length = int.from_bytes(value[offset : offset + length_size], "big")
        offset += length_size
    return value[offset : offset + length].decode("latin-1", errors="ignore")
