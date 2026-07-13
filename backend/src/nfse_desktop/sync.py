from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
from time import sleep

import httpx
from gov_nfse import Ambiente, NfseClient, summarize_nfse_xml
from gov_nfse.encoding import gzip_base64_decode_text
from gov_nfse.errors import ServerError, TooManyRequestsError

from .repository import Repository

REQUEST_DELAY_SECONDS = 5
RATE_LIMIT_DELAY_SECONDS = 70
MAX_TRANSIENT_DELAY_SECONDS = 300


class SyncService:
    def __init__(self, repository: Repository, data_dir: Path) -> None:
        self.repository = repository
        self.data_dir = data_dir

    def synchronize_pfx(self, cnpj: str, pfx: bytes, password: str) -> dict[str, object]:
        company = self.repository.get_company(cnpj)
        if not company:
            raise ValueError("Empresa nao encontrada.")

        current_nsu = max(0, int(company["last_nsu"] or 0) - 50)
        self.repository.set_sync_state(
            cnpj,
            status="syncing",
            diagnostic=f"INICIANDO | NSU {current_nsu}",
        )
        downloaded = 0

        try:
            with tempfile.TemporaryDirectory(prefix="nfse-desktop-") as temp_dir:
                certificate_path = Path(temp_dir) / "certificate.pfx"
                certificate_path.write_bytes(pfx)
                with NfseClient(
                    certificado_pfx=certificate_path,
                    senha=password,
                    ambiente=self._current_environment(),
                    timeout=90,
                ) as client:
                    transient_attempt = 0
                    while True:
                        if not self.repository.get_company(cnpj):
                            return {
                                "ok": True,
                                "diagnostic": "Empresa removida durante a sincronizacao.",
                                "downloaded": downloaded,
                            }
                        try:
                            result = client.fetch_by_nsu(
                                current_nsu,
                                cnpj_consulta=cnpj,
                                lote=True,
                            )
                        except TooManyRequestsError:
                            diagnostic = (
                                f"HTTP 429 | NSU {current_nsu} | "
                                f"Nova tentativa em {RATE_LIMIT_DELAY_SECONDS}s"
                            )
                            self.repository.set_sync_state(
                                cnpj,
                                status="waiting",
                                diagnostic=diagnostic,
                            )
                            sleep(RATE_LIMIT_DELAY_SECONDS)
                            continue
                        except (httpx.TransportError, ServerError, OSError) as exc:
                            delay = min(
                                15 * (2**transient_attempt),
                                MAX_TRANSIENT_DELAY_SECONDS,
                            )
                            transient_attempt += 1
                            diagnostic = (
                                f"REDE | NSU {current_nsu} | {type(exc).__name__}: "
                                f"{str(exc)[:300]} | Nova tentativa em {delay}s"
                            )
                            self.repository.set_sync_state(
                                cnpj,
                                status="waiting",
                                diagnostic=diagnostic,
                            )
                            sleep(delay)
                            continue

                        transient_attempt = 0
                        diagnostic = _diagnostic(current_nsu, result)
                        no_more_documents = _is_no_documents_result(result.status, result.erros)
                        if (result.status == "REJEICAO" or result.erros) and not no_more_documents:
                            self.repository.set_sync_state(
                                cnpj,
                                status="error",
                                diagnostic=diagnostic,
                            )
                            return {"ok": False, "diagnostic": diagnostic, "downloaded": downloaded}

                        for document in result.documentos:
                            if not self.repository.get_company(cnpj):
                                return {
                                    "ok": True,
                                    "diagnostic": "Empresa removida durante a sincronizacao.",
                                    "downloaded": downloaded,
                                }
                            self._save_document(cnpj, document)
                            downloaded += 1

                        returned_nsu = int(result.ultimo_nsu or current_nsu)
                        if returned_nsu != current_nsu:
                            current_nsu = returned_nsu
                            self.repository.set_sync_state(
                                cnpj,
                                status="syncing",
                                diagnostic=diagnostic,
                                last_nsu=current_nsu,
                            )

                        if no_more_documents or not result.documentos:
                            if no_more_documents:
                                diagnostic = (
                                    f"ATUALIZADO | NSU {current_nsu} | "
                                    "Todos os documentos foram consultados"
                                )
                            self.repository.set_sync_state(
                                cnpj,
                                status="idle",
                                diagnostic=diagnostic,
                                last_nsu=current_nsu,
                            )
                            return {"ok": True, "diagnostic": diagnostic, "downloaded": downloaded}
                        sleep(REQUEST_DELAY_SECONDS)
        except Exception as exc:
            diagnostic = f"ERRO | NSU {current_nsu} | {str(exc)[:500]}"
            self.repository.set_sync_state(cnpj, status="error", diagnostic=diagnostic)
            return {"ok": False, "diagnostic": diagnostic, "downloaded": downloaded}

    def process_windows_batch(
        self,
        cnpj: str,
        requested_nsu: int,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if not self.repository.get_company(cnpj):
            raise ValueError("Empresa nao encontrada.")

        status = str(payload.get("StatusProcessamento") or "DESCONHECIDO")
        raw_documents = payload.get("LoteDFe") or []
        raw_errors = payload.get("Erros") or []
        if not isinstance(raw_documents, list) or not isinstance(raw_errors, list):
            raise ValueError("Resposta invalida recebida do ADN.")

        returned_nsu = requested_nsu
        downloaded = 0
        for item in raw_documents:
            if not isinstance(item, dict):
                continue
            nsu = int(item.get("NSU") or 0)
            returned_nsu = max(returned_nsu, nsu)
            encoded_xml = item.get("ArquivoXml")
            xml = gzip_base64_decode_text(encoded_xml) if isinstance(encoded_xml, str) else ""
            document = SimpleNamespace(
                nsu=nsu,
                chave_acesso=str(item.get("ChaveAcesso") or ""),
                tipo_documento=str(item.get("TipoDocumento") or ""),
                tipo_evento=item.get("TipoEvento"),
                xml=xml,
            )
            self._save_document(cnpj, document)
            downloaded += 1

        error_summaries = [
            f"{error.get('Codigo', 'SEM_CODIGO')}: {error.get('Descricao', 'Erro sem descricao')}"
            for error in raw_errors[:3]
            if isinstance(error, dict)
        ]
        parts = [
            f"API {status}",
            f"NSU solicitado {requested_nsu}",
            f"NSU retornado {returned_nsu}",
            f"Documentos {downloaded}",
        ]
        if error_summaries:
            parts.append("Erros " + " | ".join(error_summaries))
        diagnostic = " | ".join(parts)[:600]
        no_more_documents = _is_no_documents_payload(status, raw_errors)
        if no_more_documents:
            diagnostic = (
                f"ATUALIZADO | NSU {returned_nsu} | "
                "Todos os documentos foram consultados"
            )
        has_error = (status == "REJEICAO" or bool(raw_errors)) and not no_more_documents
        should_continue = not has_error and downloaded > 0 and returned_nsu > requested_nsu
        self.repository.set_sync_state(
            cnpj,
            status="syncing" if should_continue else ("error" if has_error else "idle"),
            diagnostic=diagnostic,
            last_nsu=returned_nsu,
        )
        return {
            "ok": not has_error,
            "continue": should_continue,
            "last_nsu": returned_nsu,
            "downloaded": downloaded,
            "diagnostic": diagnostic,
        }

    def _save_document(self, cnpj: str, document: object) -> None:
        document_type = str(getattr(document, "tipo_documento"))
        xml = str(getattr(document, "xml"))
        nsu = int(getattr(document, "nsu"))
        access_key = str(getattr(document, "chave_acesso") or f"nsu-{nsu}")
        settings = self.repository.get_settings()
        xml_dir = Path(settings["notes_directory"]) / cnpj / "xml"
        xml_dir.mkdir(parents=True, exist_ok=True)
        xml_path = xml_dir / f"{nsu:012d}-{access_key}.xml"
        xml_path.write_text(xml, encoding="utf-8")

        if document_type == "NFSE":
            summary = summarize_nfse_xml(xml)
            direction = summary.classificar_para_cnpj(cnpj)
            item = {
                "note_number": summary.numero,
                "issued_at": summary.geracao.isoformat() if summary.geracao else None,
                "issuer_name": summary.emitente_nome,
                "customer_name": summary.tomador_nome,
                "service_amount": summary.valor_servico,
                "net_amount": summary.valor_liquido,
            }
        else:
            direction = "event"
            item = {}

        self.repository.save_document(
            {
                "company_cnpj": cnpj,
                "nsu": nsu,
                "access_key": access_key,
                "note_number": item.get("note_number"),
                "document_type": document_type,
                "event_type": getattr(document, "tipo_evento", None),
                "direction": direction,
                "status": "",
                "xml_path": str(xml_path),
                **item,
            }
        )

    def _current_environment(self) -> Ambiente:
        value = str(self.repository.get_settings().get("environment") or Ambiente.PRODUCAO)
        try:
            return Ambiente(value)
        except ValueError:
            return Ambiente.PRODUCAO


def _diagnostic(requested_nsu: int, result: object) -> str:
    status = str(getattr(result, "status", "DESCONHECIDO"))
    returned_nsu = int(getattr(result, "ultimo_nsu", requested_nsu) or requested_nsu)
    documents = list(getattr(result, "documentos", []) or [])
    errors = list(getattr(result, "erros", []) or [])
    parts = [
        f"API {status}",
        f"NSU solicitado {requested_nsu}",
        f"NSU retornado {returned_nsu}",
        f"Documentos {len(documents)}",
    ]
    if errors:
        parts.append(
            "Erros "
            + " | ".join(
                f"{getattr(error, 'codigo', 'SEM_CODIGO')}: "
                f"{getattr(error, 'descricao', 'Erro sem descricao')}"
                for error in errors[:3]
            )
        )
    return " | ".join(parts)[:600]


def _is_no_documents_result(status: str, errors: list[object]) -> bool:
    return status == "NENHUM_DOCUMENTO_LOCALIZADO" and all(
        str(getattr(error, "codigo", "")) == "E2220" for error in errors
    )


def _is_no_documents_payload(status: str, errors: list[object]) -> bool:
    return status == "NENHUM_DOCUMENTO_LOCALIZADO" and all(
        isinstance(error, dict) and str(error.get("Codigo", "")) == "E2220"
        for error in errors
    )
