from __future__ import annotations


class GovNfseError(Exception):
    """Base para erros da biblioteca."""


class CertificateError(GovNfseError):
    """Erro ao carregar ou usar certificado digital."""


class InvalidCertificatePasswordError(CertificateError):
    """Senha do PFX/P12 incorreta ou certificado inacessivel."""


class HttpError(GovNfseError):
    def __init__(self, status_code: int, message: str, *, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class UnauthorizedError(HttpError):
    pass


class ForbiddenError(HttpError):
    pass


class NotFoundError(HttpError):
    pass


class TooManyRequestsError(HttpError):
    pass


class ServerError(HttpError):
    pass


class InvalidResponseError(GovNfseError):
    """Resposta fora do formato esperado."""
