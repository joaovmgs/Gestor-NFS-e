from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ProcessingMessage:
    codigo: str
    descricao: str
    complemento: str | None = None


@dataclass(frozen=True)
class DistributedDocument:
    nsu: int
    chave_acesso: str
    tipo_documento: str
    xml: str
    data_hora_geracao: datetime | None = None
    tipo_evento: str | None = None


@dataclass(frozen=True)
class NsuQueryResult:
    status: str
    documentos: list[DistributedDocument]
    ultimo_nsu: int
    alertas: list[ProcessingMessage] = field(default_factory=list)
    erros: list[ProcessingMessage] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NfseXmlResult:
    chave_acesso: str
    xml: str
    raw: dict[str, Any]
