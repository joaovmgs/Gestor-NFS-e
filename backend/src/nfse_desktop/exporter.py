from __future__ import annotations

import re
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from danfse_brasil import parse_danfse, render_danfse_pdf

from .report import generate_nfse_report_xlsx
from .repository import Repository


class DocumentExporter:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def create_zip(
        self,
        cnpj: str,
        *,
        start_date: str,
        end_date: str,
        direction: str,
        search: str | None = None,
        status: str | None = None,
        include_xml: bool = True,
        include_pdf: bool = True,
        include_xlsx: bool = True,
    ) -> tuple[Path, int]:
        if not any((include_xml, include_pdf, include_xlsx)):
            raise ValueError("Selecione ao menos um formato para exportar.")
        documents = self.repository.list_documents_for_export(
            cnpj,
            start_date=start_date,
            end_date=end_date,
            direction=direction,
            search=search,
            status=status,
        )
        temp_zip = NamedTemporaryFile(delete=False, suffix=".zip")
        temp_zip.close()
        zip_path = Path(temp_zip.name)

        try:
            with TemporaryDirectory(prefix="gestor-nfse-pdf-") as pdf_directory:
                pdf_root = Path(pdf_directory)
                warnings: list[str] = []
                with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
                    for document in documents:
                        xml_path = Path(str(document["xml_path"]))
                        if not xml_path.is_file():
                            warnings.append(
                                f"{_document_name(document, xml_path)}: arquivo XML local nao encontrado."
                            )
                            continue
                        base_name = _document_name(document, xml_path)
                        cancelled = str(document.get("status") or "").lower() == "cancelada"
                        xml_folder = "xml/canceladas" if cancelled else "xml"
                        pdf_folder = "pdf/canceladas" if cancelled else "pdf"
                        if include_xml:
                            archive.write(xml_path, arcname=f"{xml_folder}/{base_name}.xml")

                        if include_pdf:
                            pdf_path = pdf_root / f"{base_name}.pdf"
                            try:
                                _render_pdf(xml_path, pdf_path)
                                archive.write(
                                    pdf_path,
                                    arcname=f"{pdf_folder}/{base_name}.pdf",
                                    compress_type=ZIP_STORED,
                                )
                            except Exception as exc:
                                warnings.append(
                                    f"{base_name}: PDF nao gerado ({str(exc)[:200]})."
                                )
                            finally:
                                pdf_path.unlink(missing_ok=True)

                    if include_xlsx:
                        company = self.repository.get_company(cnpj)
                        if company is None:
                            raise ValueError("Empresa não encontrada.")
                        report_path = generate_nfse_report_xlsx(
                            company=company,
                            tipo=f"{direction}s",
                            data_inicial=start_date,
                            data_final=end_date,
                            situacao=status,
                            query=search,
                            documents=documents,
                        )
                        try:
                            archive.write(
                                report_path,
                                arcname="relatorio-retencoes-nfse.xlsx",
                                compress_type=ZIP_STORED,
                            )
                        finally:
                            report_path.unlink(missing_ok=True)

                    if warnings:
                        archive.writestr(
                            "avisos-exportacao.txt",
                            "Alguns arquivos não puderam ser incluídos:\n\n"
                            + "\n".join(warnings),
                        )
            return zip_path, len(documents)
        except Exception:
            zip_path.unlink(missing_ok=True)
            raise


def _render_pdf(xml_path: Path, pdf_path: Path) -> Path:
    data = parse_danfse(xml_path)
    return render_danfse_pdf(data, pdf_path)


def _document_name(document: dict[str, object], xml_path: Path) -> str:
    value = str(document.get("access_key") or xml_path.stem)
    sanitized = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-")
    return sanitized or f"nsu-{document.get('nsu', 'documento')}"
