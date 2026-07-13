from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from .certificate import A1Certificate
from .config import ENDPOINTS, Ambiente, Endpoints
from .encoding import gzip_base64_decode_text
from .errors import InvalidResponseError
from .http import HttpTransport
from .models import DistributedDocument, NfseXmlResult, NsuQueryResult, ProcessingMessage


class NfseClient:
    """Cliente de consultas para APIs da NFS-e Nacional.

    Esta versao inicial foca em leitura:
    - ADN Contribuintes: distribuicao por NSU.
    - SEFIN Nacional: consulta por chave.
    - ADN DANFSE: download do PDF oficial.
    """

    def __init__(
        self,
        *,
        certificado_pfx: str | Path,
        senha: str,
        ambiente: Ambiente = Ambiente.PRODUCAO,
        timeout: float = 60.0,
    ) -> None:
        self.ambiente = ambiente
        self.endpoints: Endpoints = ENDPOINTS[ambiente]
        self._certificate = A1Certificate(Path(certificado_pfx), senha)
        self._certificate.load()
        self._transport = HttpTransport(cert=self._certificate.httpx_cert, timeout=timeout)

    def __enter__(self) -> NfseClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._transport.close()
        self._certificate.close()

    def fetch_by_nsu(
        self,
        ultimo_nsu: int,
        *,
        cnpj_consulta: str | None = None,
        lote: bool = True,
    ) -> NsuQueryResult:
        params: dict[str, Any] = {"lote": str(lote).lower()}
        if cnpj_consulta:
            params["cnpjConsulta"] = _cnpj_identifier(cnpj_consulta)

        data = self._transport.get_json(
            f"{self.endpoints.adn}/DFe/{ultimo_nsu}",
            params=params,
            accepted_statuses={400, 404},
        )
        if "StatusProcessamento" not in data:
            raise InvalidResponseError("Resposta do ADN sem StatusProcessamento.")

        documentos = [_parse_distributed_document(item) for item in data.get("LoteDFe") or []]
        return NsuQueryResult(
            status=str(data["StatusProcessamento"]),
            documentos=documentos,
            ultimo_nsu=max([ultimo_nsu, *[doc.nsu for doc in documentos]]),
            alertas=[_parse_message(item) for item in data.get("Alertas") or []],
            erros=[_parse_message(item) for item in data.get("Erros") or []],
            raw=data,
        )

    def iter_documents_by_nsu(
        self,
        *,
        start_nsu: int = 0,
        cnpj_consulta: str | None = None,
        max_batches: int | None = None,
    ) -> Iterator[NsuQueryResult]:
        ultimo_nsu = start_nsu
        batches = 0
        while max_batches is None or batches < max_batches:
            result = self.fetch_by_nsu(ultimo_nsu, cnpj_consulta=cnpj_consulta, lote=True)
            yield result
            batches += 1
            if result.status == "NENHUM_DOCUMENTO_LOCALIZADO" or result.ultimo_nsu == ultimo_nsu:
                break
            ultimo_nsu = result.ultimo_nsu

    def fetch_by_chave(self, chave_acesso: str) -> NfseXmlResult:
        chave = _only_digits(chave_acesso)
        if len(chave) != 50:
            raise ValueError("Chave de acesso deve conter 50 digitos.")
        data = self._transport.get_json(f"{self.endpoints.sefin}/nfse/{chave}")
        b64 = data.get("nfseXmlGZipB64")
        if not isinstance(b64, str):
            raise InvalidResponseError("Resposta da SEFIN sem nfseXmlGZipB64.")
        return NfseXmlResult(chave_acesso=chave, xml=gzip_base64_decode_text(b64), raw=data)

    def consultar_danfse(self, chave_acesso: str) -> bytes:
        chave = _only_digits(chave_acesso)
        if len(chave) != 50:
            raise ValueError("Chave de acesso deve conter 50 digitos.")
        return self._transport.get_bytes(f"{self.endpoints.danfse}/danfse/{chave}")


def _parse_distributed_document(item: dict[str, Any]) -> DistributedDocument:
    xml_b64 = item.get("ArquivoXml")
    xml = gzip_base64_decode_text(xml_b64) if isinstance(xml_b64, str) and xml_b64 else ""
    return DistributedDocument(
        nsu=int(item.get("NSU") or 0),
        chave_acesso=str(item.get("ChaveAcesso") or ""),
        tipo_documento=str(item.get("TipoDocumento") or ""),
        tipo_evento=str(item["TipoEvento"]) if item.get("TipoEvento") is not None else None,
        xml=xml,
        data_hora_geracao=_parse_datetime(item.get("DataHoraGeracao")),
    )


def _parse_message(item: dict[str, Any]) -> ProcessingMessage:
    return ProcessingMessage(
        codigo=str(item.get("Codigo") or ""),
        descricao=str(item.get("Descricao") or ""),
        complemento=str(item["Complemento"]) if item.get("Complemento") is not None else None,
    )


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _only_digits(value: str) -> str:
    return "".join(char for char in value if char.isdigit())


def _cnpj_identifier(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())
