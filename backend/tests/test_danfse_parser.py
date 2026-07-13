from danfse_brasil import parse_danfse, parse_provider, validate_danfse_data


def test_provider_name_uses_normative_prest_path(tmp_path) -> None:
    xml_path = tmp_path / "nfse.xml"
    xml_path.write_text(
        """
        <NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
          <infNFSe Id="NFS123">
            <emit>
              <CNPJ>12345678000190</CNPJ>
              <xNome>Prestador no emitente</xNome>
            </emit>
            <DPS>
              <infDPS>
                <prest><CNPJ>12345678000190</CNPJ></prest>
              </infDPS>
            </DPS>
          </infNFSe>
        </NFSe>
        """,
        encoding="utf-8",
    )

    assert parse_provider(xml_path).name == "-"
    issues = validate_danfse_data(parse_danfse(xml_path))
    assert any(
        issue.code == "data.required_missing"
        and issue.severity == "warning"
        and "DPS/infDPS/prest/xNome" in issue.message
        for issue in issues
    )
