from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
import pytest

from nfse_desktop.certificates import inspect_pfx, validate_certificate_expiration


def make_pfx(
    password: str = "secret",
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA TESTE 12345678000190")]
    )
    start = not_before or datetime.now(timezone.utc) - timedelta(days=1)
    end = not_after or datetime.now(timezone.utc) + timedelta(days=365)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"test",
        key,
        certificate,
        None,
        serialization.BestAvailableEncryption(password.encode()),
    )


def test_inspect_pfx_extracts_company() -> None:
    info = inspect_pfx(make_pfx(), "secret")
    assert info.cnpj == "12345678000190"
    assert info.legal_name.startswith("EMPRESA TESTE")


def test_inspect_pfx_rejects_expired_certificate() -> None:
    pfx = make_pfx(
        not_before=datetime.now(timezone.utc) - timedelta(days=30),
        not_after=datetime.now(timezone.utc) - timedelta(days=1),
    )
    with pytest.raises(ValueError, match="vencido"):
        inspect_pfx(pfx, "secret")


def test_inspect_pfx_rejects_certificate_not_valid_yet() -> None:
    pfx = make_pfx(
        not_before=datetime.now(timezone.utc) + timedelta(days=1),
        not_after=datetime.now(timezone.utc) + timedelta(days=30),
    )
    with pytest.raises(ValueError, match="ainda nao esta valido"):
        inspect_pfx(pfx, "secret")


def test_validate_certificate_expiration_rejects_expired_windows_payload() -> None:
    expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="vencido"):
        validate_certificate_expiration(expires_at)
