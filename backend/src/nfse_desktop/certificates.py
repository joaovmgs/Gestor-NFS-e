from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

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


def validate_certificate_period(not_before: datetime, not_after: datetime) -> None:
    now = datetime.now(timezone.utc)
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
    validate_certificate_period(datetime.min.replace(tzinfo=timezone.utc), expiration)


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
    expires_at = certificate.not_valid_after_utc.astimezone(timezone.utc).isoformat()
    return CertificateInfo(
        cnpj=cnpj,
        legal_name=legal_name,
        expires_at=expires_at,
        issuer=certificate.issuer.rfc4514_string(),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
