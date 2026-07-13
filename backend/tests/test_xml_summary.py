from gov_nfse import summarize_nfse_xml


def test_summary_classifies_alphanumeric_cnpj() -> None:
    summary = summarize_nfse_xml(
        """
        <NFSe>
          <infNFSe>
            <emit><CNPJ>A8244957000100</CNPJ><xNome>Prestador</xNome></emit>
            <toma><CNPJ>B8244957000100</CNPJ><xNome>Tomador</xNome></toma>
          </infNFSe>
        </NFSe>
        """
    )

    assert summary.classificar_para_cnpj("A8.244.957/0001-00") == "emitida"
    assert summary.classificar_para_cnpj("B8.244.957/0001-00") == "recebida"
