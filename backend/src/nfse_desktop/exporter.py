from __future__ import annotations

from pathlib import Path
import re
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
    ) -> tuple[Path, int]:
        documents = self.repository.list_documents_for_export(
            cnpj,
            start_date=start_date,
            end_date=end_date,
            direction=direction,
        )
        temp_zip = NamedTemporaryFile(delete=False, suffix=".zip")
        temp_zip.close()
        zip_path = Path(temp_zip.name)

        try:
            with TemporaryDirectory(prefix="gestor-nfse-pdf-") as pdf_directory:
                pdf_root = Path(pdf_directory)
                exported_count = 0
                with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
                    for document in documents:
                        xml_path = Path(str(document["xml_path"]))
                        if not xml_path.is_file():
                            continue
                        base_name = _document_name(document, xml_path)
                        cancelled = str(document.get("status") or "").lower() == "cancelada"
                        xml_folder = "xml/canceladas" if cancelled else "xml"
                        pdf_folder = "pdf/canceladas" if cancelled else "pdf"
                        archive.write(xml_path, arcname=f"{xml_folder}/{base_name}.xml")

                        pdf_path = pdf_root / f"{base_name}.pdf"
                        try:
                            _render_pdf(xml_path, pdf_path)
                            archive.write(
                                pdf_path,
                                arcname=f"{pdf_folder}/{base_name}.pdf",
                                compress_type=ZIP_STORED,
                            )
                            exported_count += 1
                        finally:
                            pdf_path.unlink(missing_ok=True)

                    company = self.repository.get_company(cnpj)
                    if company is None:
                        raise ValueError("Empresa não encontrada.")
                    report_path = generate_nfse_report_xlsx(
                        company=company,
                        tipo=f"{direction}s",
                        data_inicial=start_date,
                        data_final=end_date,
                        situacao=None,
                        query=None,
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
            return zip_path, exported_count
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
