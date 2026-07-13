# Parametros municipais

## Decisao

O Gestor NFS-e nao consulta parametros municipais no fluxo atual de sincronizacao e exportacao.

Os endpoints de parametrizacao municipal continuam mapeados na biblioteca interna de endpoints, mas nao sao usados pela aplicacao desktop porque o escopo atual e consultar documentos fiscais ja autorizados no Ambiente de Dados Nacional, gerar PDF local e exportar XML/XLSX.

## Motivo

A documentacao oficial descreve a API de parametros municipais como apoio para obter parametrizacoes de um municipio e preencher informacoes necessarias da DPS antes da emissao. Esse uso e diferente do fluxo do Gestor NFS-e, que nao emite DPS nem transmite documentos para autorizacao.

Para consulta e download de notas ja existentes, os endpoints relevantes continuam sendo:

- ADN Contribuintes, para distribuicao por NSU.
- SEFIN Nacional, quando houver consulta por chave.
- DANFSe, quando houver necessidade de PDF oficial.

## Quando reavaliar

Reabrir esta decisao se o app passar a oferecer alguma destas funcionalidades:

- emissao ou pre-preenchimento de DPS;
- diagnostico de regras municipais antes da emissao;
- validacao assistida de aliquotas, regimes ou convenio municipal;
- cache local de parametros para emissores proprios.

## Referencias

- APIs de producao e producao restrita da NFS-e: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao
- Manual de API do Emissor Publico Nacional, secao API Parametros Municipais: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf
