from datetime import UTC, datetime
from pathlib import Path

import pytest

from nfse_desktop.database import Database
from nfse_desktop.repository import Repository
from nfse_desktop.storage import (
    REORGANIZATION_BATCH_SIZE,
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


def test_dominio_path_without_mapping_uses_provisional_folder(tmp_path: Path) -> None:
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
        direction="emitida",
    )

    assert path == (tmp_path / "Emitidas" / f"XX-EMPRESA-{CNPJ}" / "012026"
                    / "000000000042-CHAVE.xml")


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

    assert code_only.parent.parent.name == CNPJ
    assert alias_only.parent.parent.name == CNPJ


def test_invalid_issue_date_uses_sync_month_without_failing(tmp_path: Path) -> None:
    path = document_xml_path(
        str(tmp_path),
        cnpj=CNPJ,
        nsu=1,
        access_key="A",
        document_type="NFSE",
        issued_at="data-invalida",
        dominio_enabled=True,
        dominio_code="40",
        dominio_alias="EMPRESA",
        direction="emitida",
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


def test_resolved_mapping_automatically_moves_only_provisional_xmls(tmp_path):
    repository = make_repository(tmp_path)
    root = tmp_path / "Notas"
    repository.update_settings(str(root), True, True)
    repository.update_company_settings(CNPJ, dominio_code="40", dominio_alias="OFICIAL")
    provisional = root / "Recebidas" / f"XX-EMPRESA-{CNPJ}" / "012026" / "old.xml"
    existing = root / "Recebidas" / "40-ANTIGO" / "012026" / "keep.xml"
    for nsu, source in enumerate((provisional, existing), 1):
        source.parent.mkdir(parents=True)
        source.write_text("<NFSe />", encoding="utf-8")
        repository.save_document({
            "company_cnpj": CNPJ, "nsu": nsu, "access_key": f"KEY-{nsu}",
            "document_type": "NFSE", "direction": "recebida", "issued_at": "2026-01-20",
            "xml_path": str(source),
        })
    result = reorganize_company_xmls(repository, CNPJ, provisional_only=True)
    assert result["total"] == result["moved"] == 1
    assert result["errors"] == 0
    assert existing.exists()
    assert not provisional.exists()
    destination = root / "Recebidas" / "40-OFICIAL" / "012026" / "000000000001-KEY-1.xml"
    assert destination.read_text(encoding="utf-8") == "<NFSe />"
    assert repository.list_company_nfse_documents(CNPJ)[0]["xml_path"] == str(destination)


@pytest.mark.parametrize("direction,folder", [("emitida", "Emitidas"), ("recebida", "Recebidas")])
def test_reorganize_moves_known_nfse_and_updates_database(tmp_path: Path, direction, folder) -> None:
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
            "direction": direction,
            "issued_at": "2026-01-20T10:00:00-03:00",
            "xml_path": str(old_path),
        }
    )

    result = reorganize_company_xmls(repository, CNPJ)

    expected = tmp_path / "Notas" / folder / "40-CAPITAL TRADE" / "012026" / old_path.name
    assert result == {
        "state": "completed",
        "total": 1,
        "processed": 1,
        "moved": 1,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }
    assert expected.read_text(encoding="utf-8") == "<NFSe />"
    assert not old_path.exists()
    stored = repository.list_company_nfse_documents(CNPJ)
    assert stored[0]["xml_path"] == str(expected)


def test_reorganize_does_not_overwrite_different_file(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.update_company_settings(CNPJ, dominio_code="40", dominio_alias="EMPRESA")
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
        / "Emitidas"
        / "40-EMPRESA"
        / "012026"
        / "000000000001-CHAVE.xml"
    )
    destination.parent.mkdir(parents=True)
    destination.write_text("destino diferente", encoding="utf-8")

    result = reorganize_company_xmls(repository, CNPJ)

    assert result["errors"] == 1
    assert old_path.read_text(encoding="utf-8") == "origem"
    assert destination.read_text(encoding="utf-8") == "destino diferente"


def test_large_reorganization_updates_database_in_batches(tmp_path: Path) -> None:
    class BatchRepository:
        def __init__(self) -> None:
            self.update_calls: list[list[tuple[str, int]]] = []
            self.documents = []
            for index in range(REORGANIZATION_BATCH_SIZE * 2 + 1):
                source = tmp_path / "legacy" / f"{index}.xml"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(f"<NFSe id='{index}' />", encoding="utf-8")
                self.documents.append(
                    {
                        "id": index + 1,
                        "nsu": index + 1,
                        "access_key": f"CHAVE-{index}",
                        "direction": "recebida",
                        "issued_at": "2026-01-20",
                        "xml_path": str(source),
                    }
                )

        def get_settings(self):
            return {
                "dominio_folder_layout_enabled": True,
                "notes_directory": str(tmp_path / "Notas"),
            }

        def get_company(self, _cnpj):
            return {"dominio_code": "40", "dominio_alias": "EMPRESA"}

        def list_company_nfse_documents(self, _cnpj):
            return self.documents

        def update_document_xml_paths(self, updates):
            self.update_calls.append(list(updates))

    repository = BatchRepository()

    result = reorganize_company_xmls(repository, CNPJ)

    assert result["state"] == "completed"
    assert result["processed"] == REORGANIZATION_BATCH_SIZE * 2 + 1
    assert result["moved"] == REORGANIZATION_BATCH_SIZE * 2 + 1
    assert [len(batch) for batch in repository.update_calls] == [
        REORGANIZATION_BATCH_SIZE,
        REORGANIZATION_BATCH_SIZE,
        1,
    ]


def test_reorganization_recovers_interrupted_layout_and_preserves_source_on_db_failure(
    tmp_path, monkeypatch,
):
    repository = make_repository(tmp_path)
    notes = tmp_path / "Notas"
    repository.update_settings(str(notes), True, True)
    repository.update_company_settings(CNPJ, dominio_code="40", dominio_alias="EMPRESA")
    missing_path = notes / "40-EMPRESA" / "012026" / "000000000001-CHAVE.xml"
    actual = missing_path.parent / "Recebidas" / missing_path.name
    actual.parent.mkdir(parents=True)
    actual.write_text("<NFSe />", encoding="utf-8")
    repository.save_document({
        "company_cnpj": CNPJ, "nsu": 1, "access_key": "CHAVE", "document_type": "NFSE",
        "direction": "recebida", "issued_at": "2026-01-20", "xml_path": str(missing_path),
    })
    original_update = repository.update_document_xml_paths

    def fail(_updates):
        raise RuntimeError("Simulated database write failure")

    monkeypatch.setattr(repository, "update_document_xml_paths", fail)
    result = reorganize_company_xmls(repository, CNPJ)
    assert result["errors"] == 1
    assert actual.read_text(encoding="utf-8") == "<NFSe />"
    destination = notes / "Recebidas" / "40-EMPRESA" / "012026" / missing_path.name
    assert not destination.exists()
    monkeypatch.setattr(repository, "update_document_xml_paths", original_update)
    result = reorganize_company_xmls(repository, CNPJ)
    assert result["errors"] == 0
    assert destination.read_text(encoding="utf-8") == "<NFSe />"
    assert not actual.exists()
    assert repository.list_company_nfse_documents(CNPJ)[0]["xml_path"] == str(destination)
