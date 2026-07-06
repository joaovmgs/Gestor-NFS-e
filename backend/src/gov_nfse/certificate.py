from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from .errors import CertificateError, InvalidCertificatePasswordError


@dataclass
class A1Certificate:
    pfx_path: Path
    password: str
    _temp_dir: tempfile.TemporaryDirectory[str] | None = None
    cert_file: Path | None = None
    key_file: Path | None = None

    def __enter__(self) -> A1Certificate:
        self.load()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def load(self) -> None:
        if self.cert_file and self.key_file:
            return

        try:
            pfx_bytes = self.pfx_path.read_bytes()
            private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                pfx_bytes,
                self.password.encode("utf-8"),
            )
        except ValueError as exc:
            raise InvalidCertificatePasswordError(
                "Senha do certificado invalida ou PFX corrompido."
            ) from exc
        except OSError as exc:
            raise CertificateError(f"Nao foi possivel ler o certificado: {self.pfx_path}") from exc

        if private_key is None or certificate is None:
            raise CertificateError("PFX nao contem chave privada e certificado.")

        self._temp_dir = tempfile.TemporaryDirectory(prefix="gov-nfse-cert-")
        temp_path = Path(self._temp_dir.name)
        self.cert_file = temp_path / "cert.pem"
        self.key_file = temp_path / "key.pem"

        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        for cert in additional_certificates or []:
            cert_pem += cert.public_bytes(serialization.Encoding.PEM)

        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

        self.cert_file.write_bytes(cert_pem)
        self.key_file.write_bytes(key_pem)

    @property
    def httpx_cert(self) -> tuple[str, str]:
        self.load()
        if not self.cert_file or not self.key_file:
            raise CertificateError("Certificado nao carregado.")
        return (str(self.cert_file), str(self.key_file))

    def close(self) -> None:
        if self._temp_dir:
            self._temp_dir.cleanup()
        self._temp_dir = None
        self.cert_file = None
        self.key_file = None
