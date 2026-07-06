from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
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


def _cnpj_from_certificate(certificate: x509.Certificate) -> str:
    try:
        extension = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for other_name in extension.value.get_values_for_type(x509.OtherName):
            if other_name.type_id == CNPJ_OID:
                digits = re.sub(r"\D", "", _decode_der_string(other_name.value))
                if len(digits) == 14:
                    return digits
    except x509.ExtensionNotFound:
        pass

    digits = re.findall(r"\d{14}", certificate.subject.rfc4514_string())
    return digits[0] if digits else ""


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

