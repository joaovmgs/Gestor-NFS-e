from io import BytesIO
from zipfile import ZipFile

from openpyxl import load_workbook

from nfse_desktop.database import Database
from nfse_desktop.exporter import DocumentExporter
from nfse_desktop.repository import Repository


def test_export_zip_separates_cancelled_documents(tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "export.db")
    database.initialize()
    repository = Repository(database)
    repository.initialize_settings(str(tmp_path / "Notas"))
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

    normal_xml = tmp_path / "normal.xml"
    cancelled_xml = tmp_path / "cancelada.xml"
    normal_xml.write_text(
        """
        <NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
          <infNFSe>
            <nNFSe>123</nNFSe>
            <DPS>
              <infDPS>
                <finNFSe>1</finNFSe>
                <tpNFSeDebito>2</tpNFSeDebito>
                <tpNFSeCredito>3</tpNFSeCredito>
                <valores>
                  <vServPrest><vServ>100.00</vServ></vServPrest>
                  <trib>
                    <tribFed>
                      <vRetIRRF>1.10</vRetIRRF>
                      <vRetCSLL>2.20</vRetCSLL>
                      <vRetCP>3.30</vRetCP>
                    </tribFed>
                    <tribMun><tpRetISSQN>2</tpRetISSQN></tribMun>
                  </trib>
                </valores>
                <IBSCBS>
                  <valores>
                    <trib>
                      <gIBSCBSAjuste>
                        <vIBS>4.40</vIBS>
                        <vCBS>5.50</vCBS>
                      </gIBSCBSAjuste>
                    </trib>
                  </valores>
                </IBSCBS>
              </infDPS>
            </DPS>
            <valores>
              <vISSQN>6.60</vISSQN>
              <vLiq>80.00</vLiq>
            </valores>
            <IBSCBS>
              <totCIBS>
                <gIBS><vIBSTot>7.70</vIBSTot></gIBS>
                <gCBS><vCBS>8.80</vCBS></gCBS>
              </totCIBS>
            </IBSCBS>
          </infNFSe>
        </NFSe>
        """,
        encoding="utf-8",
    )
    cancelled_xml.write_text("<NFSe/>", encoding="utf-8")
    base = {
        "company_cnpj": "12345678000190",
        "document_type": "NFSE",
        "event_type": None,
        "direction": "emitida",
        "issued_at": "2026-07-03T10:00:00",
        "issuer_name": "Prestador",
        "customer_name": "Tomador",
        "service_amount": 100.0,
        "net_amount": 90.0,
    }
    repository.save_document(
        {
            **base,
            "nsu": 1,
            "access_key": "CHAVE-NORMAL",
            "status": "",
            "xml_path": str(normal_xml),
        }
    )
    repository.save_document(
        {
            **base,
            "nsu": 2,
            "access_key": "CHAVE-CANCELADA",
            "status": "Cancelada",
            "xml_path": str(cancelled_xml),
        }
    )

    monkeypatch.setattr("nfse_desktop.exporter.parse_danfse", lambda _path: object())

    def fake_render(_data, output):
        output.write_bytes(b"%PDF-1.4 test")
        return output

    monkeypatch.setattr("nfse_desktop.exporter.render_danfse_pdf", fake_render)
    zip_path, count = DocumentExporter(repository).create_zip(
        "12345678000190",
        start_date="2026-07-01",
        end_date="2026-07-31",
        direction="emitida",
    )

    try:
        with ZipFile(zip_path) as archive:
            assert set(archive.namelist()) == {
                "xml/CHAVE-NORMAL.xml",
                "pdf/CHAVE-NORMAL.pdf",
                "xml/canceladas/CHAVE-CANCELADA.xml",
                "pdf/canceladas/CHAVE-CANCELADA.pdf",
                "relatorio-retencoes-nfse.xlsx",
            }
            workbook = load_workbook(
                BytesIO(archive.read("relatorio-retencoes-nfse.xlsx")),
                data_only=False,
            )
            sheet = workbook["Retencoes NFS-e"]
            assert sheet["A1"].value == "RELATÓRIO DE RETENÇÕES DE NFS-e"
            assert sheet["A6"].value == "Número da NFS-e"
            assert sheet["B6"].value == "Situação"
            assert sheet["B7"].value == "Autorizada"
            assert sheet["B8"].value == "Cancelada"
            assert sheet["C6"].value == "Finalidade da NFS-e (finNFSe)"
            assert sheet["C7"].value == "1"
            assert sheet["D7"].value == "2"
            assert sheet["E7"].value == "3"
            assert sheet["G6"].value == "IRRF retido (vRetIRRF)"
            assert sheet["K6"].value == "Valor IBS (vIBSTot)"
            assert sheet["K7"].value == 7.7
            assert sheet["L7"].value == 8.8
            assert sheet["M7"].value == 4.4
            assert sheet["N7"].value == 5.5
            assert sheet["O6"].value == "Valor líquido (vLiq)"
        assert count == 2
    finally:
        zip_path.unlink(missing_ok=True)
