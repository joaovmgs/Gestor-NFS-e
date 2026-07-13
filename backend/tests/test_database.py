from nfse_desktop.database import Database
from nfse_desktop.api import _save_company_variants
from nfse_desktop.repository import Repository
from nfse_desktop.sync import SyncService


def test_company_round_trip(tmp_path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    repository = Repository(database)
    repository.initialize_settings(str(tmp_path / "Notas"))
    repository.save_company(
        {
            "cnpj": "12345678000190",
            "legal_name": "Empresa Teste",
            "certificate_source": "pfx",
            "certificate_cnpj": "12345678000414",
            "remember_certificate": False,
            "certificate_reference": None,
            "certificate_expires_at": "2030-01-01T00:00:00Z",
        }
    )

    company = repository.get_company("12345678000190")
    assert company is not None
    assert company["legal_name"] == "Empresa Teste"
    assert company["certificate_cnpj"] == "12345678000414"
    assert company["last_nsu"] == 0
    settings = repository.get_settings()
    assert settings["notes_directory"] == str(tmp_path / "Notas")
    assert settings["notifications_enabled"] is True
    assert settings["environment"] == "producao"

    repository.update_settings(
        str(tmp_path / "Notas Restritas"),
        notifications_enabled=False,
        environment="producao_restrita",
    )
    updated_settings = repository.get_settings()
    assert updated_settings["notes_directory"] == str(tmp_path / "Notas Restritas")
    assert updated_settings["notifications_enabled"] is False
    assert updated_settings["environment"] == "producao_restrita"

    documents = repository.list_documents("12345678000190")
    assert documents["items"] == []
    assert documents["total"] == 0
    assert documents["pages"] == 1

    repository.set_sync_state(
        "12345678000190",
        status="waiting",
        diagnostic="Timeout. Nova tentativa em 15s.",
    )
    logs = repository.list_sync_logs("12345678000190")
    assert logs[0]["level"] == "warning"
    assert "15s" in logs[0]["message"]

    for index in range(25):
        repository.add_sync_log("12345678000190", "info", f"Evento {index}")

    retained_logs = repository.list_sync_logs("12345678000190", 100)
    assert len(retained_logs) == 20
    assert retained_logs[0]["message"] == "Evento 24"
    assert retained_logs[-1]["message"] == "Evento 5"


def test_cancellation_event_updates_nfse_status(tmp_path) -> None:
    database = Database(tmp_path / "events.db")
    database.initialize()
    repository = Repository(database)
    repository.save_company(
        {
            "cnpj": "12345678000190",
            "legal_name": "Empresa Teste",
            "certificate_source": "pfx",
            "remember_certificate": False,
            "certificate_reference": None,
            "certificate_expires_at": "2030-01-01T00:00:00Z",
        }
    )
    base_document = {
        "company_cnpj": "12345678000190",
        "access_key": "CHAVE-TESTE",
        "issued_at": "2026-07-02T10:00:00",
        "issuer_name": "Prestador",
        "customer_name": "Tomador",
        "service_amount": 100.0,
        "net_amount": 90.0,
        "xml_path": "nota.xml",
        "status": "",
    }
    repository.save_document(
        {
            **base_document,
            "nsu": 1,
            "document_type": "NFSE",
            "event_type": None,
            "direction": "emitida",
        }
    )
    repository.save_document(
        {
            **base_document,
            "nsu": 2,
            "document_type": "EVENTO",
            "event_type": "CANCELAMENTO",
            "direction": "event",
            "xml_path": "evento.xml",
        }
    )

    documents = repository.list_documents(
        "12345678000190",
        direction="emitida",
    )
    assert documents["items"][0]["status"] == "Cancelada"

    reverse_document = {**base_document, "access_key": "CHAVE-ORDEM-INVERSA"}
    repository.save_document(
        {
            **reverse_document,
            "nsu": 3,
            "document_type": "EVENTO",
            "event_type": "CANCELAMENTO",
            "direction": "event",
            "xml_path": "evento-anterior.xml",
        }
    )
    repository.save_document(
        {
            **reverse_document,
            "nsu": 4,
            "document_type": "NFSE",
            "event_type": None,
            "direction": "emitida",
            "xml_path": "nota-posterior.xml",
        }
    )

    reverse_result = repository.list_documents(
        "12345678000190",
        direction="emitida",
    )
    assert all(document["status"] == "Cancelada" for document in reverse_result["items"])


def test_delete_company_removes_database_history(tmp_path) -> None:
    database = Database(tmp_path / "delete-company.db")
    database.initialize()
    repository = Repository(database)
    repository.save_company(
        {
            "cnpj": "12345678000190",
            "legal_name": "Empresa Teste",
            "certificate_source": "pfx",
            "remember_certificate": True,
            "certificate_reference": "credential.bin",
            "certificate_expires_at": "2030-01-01T00:00:00Z",
        }
    )
    repository.save_document(
        {
            "company_cnpj": "12345678000190",
            "nsu": 1,
            "access_key": "CHAVE-TESTE",
            "note_number": "100",
            "document_type": "NFSE",
            "event_type": None,
            "direction": "emitida",
            "issued_at": "2026-07-03T10:00:00",
            "issuer_name": "Prestador",
            "customer_name": "Tomador",
            "service_amount": 150.75,
            "net_amount": 140.0,
            "status": "",
            "xml_path": "nota.xml",
        }
    )
    repository.add_sync_log("12345678000190", "info", "Consulta iniciada")

    assert repository.delete_company("12345678000190") is True
    assert repository.get_company("12345678000190") is None
    assert repository.list_documents("12345678000190")["total"] == 0
    assert repository.list_sync_logs("12345678000190") == []
    assert repository.delete_company("12345678000190") is False


def test_company_batch_requires_confirmation_before_partial_save(tmp_path) -> None:
    database = Database(tmp_path / "batch-company.db")
    database.initialize()
    repository = Repository(database)

    preview = _save_company_variants(
        repository,
        certificate_cnpj="08244957000438",
        legal_name="Prime Teste",
        certificate_source="pfx",
        remember_certificate=True,
        certificate_reference=None,
        certificate_expires_at="2027-03-02T00:00:00Z",
        requested_cnpjs=["08244957000100", "12345678000190"],
        allow_partial=False,
    )

    assert preview["has_invalid"] is True
    assert preview["valid_cnpjs"] == ["08244957000100"]
    assert repository.list_companies() == []

    saved = _save_company_variants(
        repository,
        certificate_cnpj="08244957000438",
        legal_name="Prime Teste",
        certificate_source="pfx",
        remember_certificate=True,
        certificate_reference=None,
        certificate_expires_at="2027-03-02T00:00:00Z",
        requested_cnpjs=["08244957000100", "12345678000190"],
        allow_partial=True,
    )

    assert saved["has_invalid"] is True
    assert [company["cnpj"] for company in saved["companies"]] == ["08244957000100"]
    assert repository.get_company("08244957000100")["certificate_cnpj"] == "08244957000438"
    assert repository.get_company("12345678000190") is None


def test_e2220_finishes_sync_without_error(tmp_path) -> None:
    database = Database(tmp_path / "sync.db")
    database.initialize()
    repository = Repository(database)
    repository.initialize_settings(str(tmp_path / "Notas"))
    repository.save_company(
        {
            "cnpj": "12345678000190",
            "legal_name": "Empresa Teste",
            "certificate_source": "windows",
            "remember_certificate": True,
            "certificate_reference": "THUMBPRINT",
            "certificate_expires_at": "2030-01-01T00:00:00Z",
        }
    )
    service = SyncService(repository, tmp_path)

    result = service.process_windows_batch(
        "12345678000190",
        10364,
        {
            "StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
            "LoteDFe": [],
            "Erros": [
                {
                    "Codigo": "E2220",
                    "Descricao": "Nenhum documento localizado",
                }
            ],
        },
    )

    assert result["ok"] is True
    assert result["continue"] is False
    assert str(result["diagnostic"]).startswith("ATUALIZADO")
    assert repository.get_company("12345678000190")["sync_status"] == "idle"


def test_document_search_and_status_filter_are_applied_before_pagination(tmp_path) -> None:
    database = Database(tmp_path / "filters.db")
    database.initialize()
    repository = Repository(database)
    repository.save_company(
        {
            "cnpj": "12345678000190",
            "legal_name": "Empresa Teste",
            "certificate_source": "pfx",
            "remember_certificate": False,
            "certificate_reference": None,
            "certificate_expires_at": "2030-01-01T00:00:00Z",
        }
    )
    for index, status in ((1, ""), (2, "Cancelada")):
        repository.save_document(
            {
                "company_cnpj": "12345678000190",
                "nsu": index,
                "access_key": f"CHAVE-{index}",
                "note_number": f"2026000{index}",
                "document_type": "NFSE",
                "event_type": None,
                "direction": "emitida",
                "issued_at": "2026-07-03T10:00:00",
                "issuer_name": "Prestador Alfa",
                "customer_name": "Tomador Beta",
                "service_amount": 150.75 + index,
                "net_amount": 140.0,
                "status": status,
                "xml_path": f"nota-{index}.xml",
            }
        )

    assert repository.list_documents(
        "12345678000190", search="20260002"
    )["items"][0]["note_number"] == "20260002"
    assert repository.list_documents(
        "12345678000190", search="Tomador Beta"
    )["total"] == 2
    assert repository.list_documents(
        "12345678000190", search="151.75"
    )["total"] == 1
    assert repository.list_documents(
        "12345678000190", status="cancelada"
    )["total"] == 1
    assert repository.list_documents(
        "12345678000190", status="autorizada"
    )["total"] == 1


def test_backfill_missing_note_numbers(tmp_path) -> None:
    xml_path = tmp_path / "nota.xml"
    xml_path.write_text(
        """
        <NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
          <infNFSe><nNFSe>9876</nNFSe></infNFSe>
        </NFSe>
        """,
        encoding="utf-8",
    )
    database = Database(tmp_path / "backfill.db")
    database.initialize()
    repository = Repository(database)
    repository.save_company(
        {
            "cnpj": "12345678000190",
            "legal_name": "Empresa Teste",
            "certificate_source": "pfx",
            "remember_certificate": False,
            "certificate_reference": None,
            "certificate_expires_at": "2030-01-01T00:00:00Z",
        }
    )
    repository.save_document(
        {
            "company_cnpj": "12345678000190",
            "nsu": 1,
            "access_key": "CHAVE-SEM-NUMERO",
            "document_type": "NFSE",
            "event_type": None,
            "direction": "emitida",
            "status": "",
            "xml_path": str(xml_path),
        }
    )

    database.backfill_note_numbers()

    document = repository.list_documents("12345678000190")["items"][0]
    assert document["note_number"] == "9876"
