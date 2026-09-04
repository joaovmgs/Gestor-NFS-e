from io import BytesIO
from zipfile import ZipFile

from openpyxl import load_workbook

from nfse_desktop.database import Database
from nfse_desktop.exporter import DocumentExporter
from nfse_desktop.report import generate_nfse_report_xlsx
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
            <xTribNac>Consultoria em tecnologia.</xTribNac>
            <DPS>
              <infDPS>
                <dhEmi>2026-07-03T10:00:00-03:00</dhEmi>
                <finNFSe>1</finNFSe>
                <tpNFSeDebito>2</tpNFSeDebito>
                <tpNFSeCredito>3</tpNFSeCredito>
                <prest>
                  <CNPJ>12345678000190</CNPJ>
                  <xNome>Empresa Teste</xNome>
                </prest>
                <toma>
                  <CNPJ>98765432000100</CNPJ>
                  <xNome>Cliente da Empresa</xNome>
                </toma>
                <serv>
                  <cServ>
                    <cTribNac>010501</cTribNac>
                    <cTribMun>1234</cTribMun>
                    <xDescServ>Consultoria mensal</xDescServ>
                    <cNBS>111032100</cNBS>
                  </cServ>
                </serv>
                <valores>
                  <vServPrest><vServ>100.00</vServ></vServPrest>
                  <trib>
                    <tribFed>
                      <vRetIRRF>1.10</vRetIRRF>
                      <vRetCSLL>2.20</vRetCSLL>
                      <vRetCP>3.30</vRetCP>
                      <piscofins>
                        <vPis>9.90</vPis>
                        <vCofins>10.10</vCofins>
                      </piscofins>
                    </tribFed>
                    <tribMun>
                      <tribISSQN>1</tribISSQN>
                      <tpRetISSQN>2</tpRetISSQN>
                    </tribMun>
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
              <vBC>95.00</vBC>
              <pAliqAplic>2.00</pAliqAplic>
              <vISSQN>6.60</vISSQN>
              <vLiq>80.00</vLiq>
            </valores>
            <IBSCBS>
              <valores>
                <uf><pIBSUF>0.10</pIBSUF></uf>
                <mun><pIBSMun>0.00</pIBSMun></mun>
                <fed><pCBS>0.90</pCBS></fed>
              </valores>
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
                "relatorio-servicos-prestados.xlsx",
            }
            workbook = load_workbook(
                BytesIO(archive.read("relatorio-servicos-prestados.xlsx")),
                data_only=False,
            )
            assert workbook.sheetnames == ["Resumo", "Serviços Prestados"]
            summary = workbook["Resumo"]
            assert summary["A1"].value == "RESUMO DE SERVIÇOS PRESTADOS"
            assert summary["A8"].value == "=COUNTA('Serviços Prestados'!A9:A10)"
            assert summary["B8"].value == '=COUNTIF(\'Serviços Prestados\'!B9:B10,"Autorizada")'
            assert summary["C8"].value == '=COUNTIF(\'Serviços Prestados\'!B9:B10,"Cancelada")'
            assert summary["A12"].value == "=SUM('Serviços Prestados'!L9:L10)"
            assert summary["B12"].value == "=SUM('Serviços Prestados'!N9:N10)"
            assert summary["C12"].value == "=SUM('Serviços Prestados'!X9:X10)"
            assert summary["A16"].value == "=SUM('Serviços Prestados'!O9:O10)"
            assert summary["B16"].value == "=SUM('Serviços Prestados'!T9:T10)"
            assert summary["C16"].value == "=SUM('Serviços Prestados'!U9:U10)"
            assert summary["A20"].value == "=SUM('Serviços Prestados'!V9:V10)"
            assert summary["B20"].value == "=SUM('Serviços Prestados'!W9:W10)"
            assert summary["C20"].value == "=SUM(A20:B20)"
            sheet = workbook["Serviços Prestados"]
            assert sheet["A1"].value == "RELATÓRIO DE SERVIÇOS PRESTADOS"
            assert sheet["A8"].value == "Número da NFS-e"
            assert sheet["B8"].value == "Situação"
            assert sheet["B9"].value == "Autorizada"
            assert sheet["B10"].value == "Cancelada"
            assert sheet["C9"].value == "CHAVE-NORMAL"
            assert sheet["E8"].value == "CNPJ/CPF do tomador"
            assert sheet["E9"].value == "98.765.432/0001-00"
            assert sheet["F9"].value == "Cliente da Empresa"
            assert sheet["G9"].value == "01.05.01"
            assert sheet["H9"].value == "1234"
            assert sheet["I9"].value == "Consultoria em tecnologia."
            assert sheet["J9"].value == "Consultoria mensal"
            assert sheet["K9"].value == "1.1103.21.00"
            assert sheet["M9"].value == 0.02
            assert sheet["N9"].value == 95
            assert sheet["O9"].value == 6.6
            assert sheet["Q9"].value == 0.001
            assert sheet["R9"].value == 0
            assert sheet["S9"].value == 0.009
            assert sheet["T9"].value == 7.7
            assert sheet["U9"].value == 8.8
            assert sheet["V9"].value == 9.9
            assert sheet["W9"].value == 10.1
            assert sheet["X9"].value == 80
            assert sheet["Y9"].value
            assert sheet.column_dimensions["G"].width == 25
            assert sheet.row_dimensions[8].height == 42
        assert count == 2
    finally:
        zip_path.unlink(missing_ok=True)


def test_export_keeps_xml_when_one_pdf_fails(tmp_path, monkeypatch) -> None:
    xml_path = tmp_path / "nota.xml"
    xml_path.write_text("<NFSe/>", encoding="utf-8")

    class FakeRepository:
        def list_documents_for_export(self, *_args, **_kwargs):
            return [
                {
                    "access_key": "CHAVE-COM-FALHA",
                    "xml_path": str(xml_path),
                    "status": "",
                }
            ]

        def get_company(self, _cnpj):
            return {"cnpj": "12345678000190", "legal_name": "Empresa Teste"}

    def fail_pdf(_xml_path, _pdf_path):
        raise ValueError("campo inesperado")

    monkeypatch.setattr("nfse_desktop.exporter._render_pdf", fail_pdf)
    zip_path, count = DocumentExporter(FakeRepository()).create_zip(
        "12345678000190",
        start_date="2026-08-01",
        end_date="2026-08-31",
        direction="emitida",
        include_xlsx=False,
    )

    try:
        with ZipFile(zip_path) as archive:
            assert set(archive.namelist()) == {
                "xml/CHAVE-COM-FALHA.xml",
                "avisos-exportacao.txt",
            }
            assert "CHAVE-COM-FALHA" in archive.read("avisos-exportacao.txt").decode()
        assert count == 1
    finally:
        zip_path.unlink(missing_ok=True)


def test_received_services_report_includes_provider_and_taxation(tmp_path) -> None:
    xml_path = tmp_path / "tomada.xml"
    xml_path.write_text(
        """
        <NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
          <infNFSe Id="NFS35503081223412247000110000000600272226088748364133">
            <nNFSe>6002722</nNFSe>
            <xTribNac>Licenciamento de software.</xTribNac>
            <DPS>
              <infDPS>
                <dhEmi>2026-08-25T09:30:00-03:00</dhEmi>
                <prest>
                  <CNPJ>34122470001100</CNPJ>
                  <xNome>Prestador Nacional LTDA</xNome>
                </prest>
                <toma>
                  <CNPJ>12345678000190</CNPJ>
                  <xNome>Empresa Teste</xNome>
                </toma>
                <serv>
                  <cServ>
                    <cTribNac>010501</cTribNac>
                    <cTribMun>9988</cTribMun>
                    <xDescServ>Licença mensal</xDescServ>
                  </cServ>
                </serv>
                <valores><vServPrest><vServ>250.00</vServ></vServPrest></valores>
              </infDPS>
            </DPS>
            <valores><vLiq>250.00</vLiq></valores>
          </infNFSe>
        </NFSe>
        """,
        encoding="utf-8",
    )
    report_path = generate_nfse_report_xlsx(
        company={"cnpj": "12345678000190", "legal_name": "Empresa Teste"},
        tipo="recebidas",
        data_inicial="2026-08-01",
        data_final="2026-08-31",
        situacao="todas",
        query=None,
        documents=[
            {
                "note_number": "6002722",
                "access_key": "35503081223412247000110000000600272226088748364133",
                "issued_at": "2026-08-25T09:30:00-03:00",
                "issuer_name": "Prestador Nacional LTDA",
                "customer_name": "Empresa Teste",
                "service_amount": 250,
                "net_amount": 250,
                "status": "",
                "xml_path": str(xml_path),
            }
        ],
    )

    try:
        workbook = load_workbook(report_path, data_only=False)
        assert workbook.sheetnames == ["Resumo", "Serviços Tomados"]
        summary = workbook["Resumo"]
        assert summary["A1"].value == "RESUMO DE SERVIÇOS TOMADOS"
        assert summary["A12"].value == "=SUM('Serviços Tomados'!K9:K9)"
        assert summary["A20"].value == "=SUM('Serviços Tomados'!P9:P9)"
        assert summary["B20"].value == "=SUM('Serviços Tomados'!Q9:Q9)"
        assert summary["C20"].value == "=SUM('Serviços Tomados'!R9:R9)"
        sheet = workbook["Serviços Tomados"]
        assert sheet["A1"].value == "RELATÓRIO DE SERVIÇOS TOMADOS"
        assert sheet["C9"].value == "35503081223412247000110000000600272226088748364133"
        assert sheet["D9"].value.year == 2026
        assert sheet["E9"].value == "34.122.470/0011-00"
        assert sheet["F9"].value == "Prestador Nacional LTDA"
        assert sheet["G9"].value == "01.05.01"
        assert sheet["H9"].value == "9988"
        assert sheet["I9"].value == "Licenciamento de software."
        assert sheet["J9"].value == "Licença mensal"
        assert sheet["K9"].value == 250
        assert sheet.freeze_panes == "E9"
        assert sheet.auto_filter.ref == "A8:Z9"
        assert sheet.column_dimensions["G"].width == 25
    finally:
        report_path.unlink(missing_ok=True)
