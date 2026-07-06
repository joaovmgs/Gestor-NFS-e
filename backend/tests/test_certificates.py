from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from nfse_desktop.certificates import inspect_pfx


def make_pfx(password: str = "secret") -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA TESTE 12345678000190")]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
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

