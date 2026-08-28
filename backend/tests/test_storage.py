from datetime import UTC, datetime
from pathlib import Path

import pytest

from nfse_desktop.database import Database
from nfse_desktop.repository import Repository
from nfse_desktop.storage import (
    document_xml_path,
    reorganize_company_xmls,
    validate_dominio_configuration,
)

CNPJ = "12345678000158"


def make_repository(tmp_path: Path) -> Repository:
    repository = Repository(Database(tmp_path / "app.db"))
    repository.database.initialize()
    repository.initialize_settings(str(tmp_path / "Notas"))
    repository.save_company(
        {
            "cnpj": CNPJ,
            "legal_name": "Empresa Teste",
            "certificate_source": "pfx",
            "remember_certificate": False,
            "certificate_expires_at": "2030-01-01T00:00:00Z",
        }
    )
    return repository


def test_dominio_path_uses_unique_placeholders_and_issue_month(tmp_path: Path) -> None:
    path = document_xml_path(
        str(tmp_path),
        cnpj=CNPJ,
        nsu=42,
        access_key="CHAVE",
        document_type="NFSE",
        issued_at="2026-01-20T12:30:00-03:00",
        dominio_enabled=True,
        dominio_code=None,
        dominio_alias=None,
    )

    assert path == tmp_path / f"XX-EMPRESA-{CNPJ}" / "012026" / "000000000042-CHAVE.xml"


def test_dominio_path_combines_partial_configuration(tmp_path: Path) -> None:
    code_only = document_xml_path(
        str(tmp_path),
        cnpj=CNPJ,
        nsu=1,
        access_key="A",
        document_type="NFSE",
        issued_at="2025-12-01",
        dominio_enabled=True,
        dominio_code="40",
        dominio_alias="",
    )
    alias_only = document_xml_path(
        str(tmp_path),
        cnpj=CNPJ,
        nsu=2,
        access_key="B",
        document_type="NFSE",
        issued_at="2025-12-01",
        dominio_enabled=True,
        dominio_code="",
        dominio_alias="CAPITAL TRADE",
    )

    assert code_only.parent.parent.name == f"40-EMPRESA-{CNPJ}"
    assert alias_only.parent.parent.name == "XX-CAPITAL TRADE"


def test_invalid_issue_date_uses_sync_month_without_failing(tmp_path: Path) -> None:
    path = document_xml_path(
        str(tmp_path),
        cnpj=CNPJ,
        nsu=1,
        access_key="A",
        document_type="NFSE",
        issued_at="data-invalida",
        dominio_enabled=True,
        dominio_code=None,
        dominio_alias=None,
        fallback_at=datetime(2026, 8, 28, tzinfo=UTC),
    )

    assert path.parent.name == "082026"


def test_event_xml_keeps_legacy_layout(tmp_path: Path) -> None:
    path = document_xml_path(
        str(tmp_path),
        cnpj=CNPJ,
        nsu=3,
        access_key="EVENTO",
        document_type="EVENTO_CANCELAMENTO",
        issued_at="2026-01-20",
        dominio_enabled=True,
        dominio_code="40",
        dominio_alias="EMPRESA",
    )

    assert path == tmp_path / CNPJ / "xml" / "000000000003-EVENTO.xml"


def test_configured_alias_rejects_windows_invalid_characters() -> None:
    with pytest.raises(ValueError, match="não pode conter"):
        validate_dominio_configuration("40", "EMPRESA/TESTE", cnpj=CNPJ)


def test_reorganize_moves_known_nfse_and_updates_database(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.update_settings(
        str(tmp_path / "Notas"),
        notifications_enabled=True,
        dominio_folder_layout_enabled=True,
    )
    repository.update_company_settings(
        CNPJ,
        dominio_code="40",
        dominio_alias="CAPITAL TRADE",
    )
    old_path = tmp_path / "Notas" / CNPJ / "xml" / "000000000001-CHAVE.xml"
    old_path.parent.mkdir(parents=True)
    old_path.write_text("<NFSe />", encoding="utf-8")
    repository.save_document(
        {
            "company_cnpj": CNPJ,
            "nsu": 1,
            "access_key": "CHAVE",
            "document_type": "NFSE",
            "direction": "emitida",
            "issued_at": "2026-01-20T10:00:00-03:00",
            "xml_path": str(old_path),
        }
    )

    result = reorganize_company_xmls(repository, CNPJ)

    expected = tmp_path / "Notas" / "40-CAPITAL TRADE" / "012026" / old_path.name
    assert result == {"moved": 1, "skipped": 0, "errors": 0, "details": []}
    assert expected.read_text(encoding="utf-8") == "<NFSe />"
    assert not old_path.exists()
    stored = repository.list_company_nfse_documents(CNPJ)
    assert stored[0]["xml_path"] == str(expected)


def test_reorganize_does_not_overwrite_different_file(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.update_settings(
        str(tmp_path / "Notas"),
        notifications_enabled=True,
        dominio_folder_layout_enabled=True,
    )
    old_path = tmp_path / "old.xml"
    old_path.write_text("origem", encoding="utf-8")
    repository.save_document(
        {
            "company_cnpj": CNPJ,
            "nsu": 1,
            "access_key": "CHAVE",
            "document_type": "NFSE",
            "direction": "emitida",
            "issued_at": "2026-01-20",
            "xml_path": str(old_path),
        }
    )
    destination = (
        tmp_path
        / "Notas"
        / f"XX-EMPRESA-{CNPJ}"
        / "012026"
        / "000000000001-CHAVE.xml"
    )
    destination.parent.mkdir(parents=True)
    destination.write_text("destino diferente", encoding="utf-8")

    result = reorganize_company_xmls(repository, CNPJ)

    assert result["errors"] == 1
    assert old_path.read_text(encoding="utf-8") == "origem"
    assert destination.read_text(encoding="utf-8") == "destino diferente"
