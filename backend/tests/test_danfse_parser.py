from danfse_nt008 import parse_provider


def test_provider_name_falls_back_to_nfse_issuer(tmp_path) -> None:
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

    assert parse_provider(xml_path).name == "Prestador no emitente"
