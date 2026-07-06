from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .errors import (
    ForbiddenError,
    HttpError,
    NotFoundError,
    ServerError,
    TooManyRequestsError,
    UnauthorizedError,
)


class HttpTransport:
    def __init__(self, *, cert: tuple[str, str], timeout: float = 60.0) -> None:
        self._client = httpx.Client(
            cert=cert,
            timeout=timeout,
            http2=False,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        accepted_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(url, params=params)
        if response.status_code in (accepted_statuses or set()):
            return _json_or_raise(response)
        if 200 <= response.status_code < 300:
            return _json_or_raise(response)
        raise map_http_error(response)

    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        accepted_statuses: set[int] | None = None,
    ) -> bytes:
        response = self._client.get(url, params=params)
        if response.status_code in (accepted_statuses or set()):
            return response.content
        if 200 <= response.status_code < 300:
            return response.content
        raise map_http_error(response)


def _json_or_raise(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise HttpError(
            response.status_code,
            f"Resposta HTTP {response.status_code} nao e JSON valido.",
            body=response.text,
        ) from exc
    if not isinstance(data, dict):
        raise HttpError(response.status_code, "Resposta JSON nao e um objeto.", body=response.text)
    return data


def map_http_error(response: httpx.Response) -> HttpError:
    status = response.status_code
    body = response.text
    if status == 401:
        return UnauthorizedError(
            status,
            "Certificado nao apresentado ou nao autorizado.",
            body=body,
        )
    if status == 403:
        return ForbiddenError(
            status,
            "Consulta nao permitida para este certificado/CNPJ.",
            body=body,
        )
    if status == 404:
        return NotFoundError(status, "Registro nao encontrado.", body=body)
    if status == 429:
        return TooManyRequestsError(status, "Limite de requisicoes excedido.", body=body)
    if status >= 500:
        return ServerError(
            status,
            f"Falha temporaria no servidor da Receita: HTTP {status}.",
            body=body,
        )
    return HttpError(status, f"Erro HTTP {status}.", body=body)
