# Gestor NFS-e

<p align="center">
  <img src="public/icon.png" alt="Ícone do Gestor NFS-e" width="180">
</p>

Aplicativo desktop para baixar, consultar e organizar nota fiscal de serviço
eletrônica e notas fiscais de serviço eletrônicas do Ambiente de Dados Nacional
da NFS-e.

[![Windows](https://img.shields.io/badge/Windows-10%20e%2011-0078D4?logo=windows)](https://github.com/joaovmgs/Gestor-NFS-e/releases/latest)
[![CI](https://github.com/joaovmgs/Gestor-NFS-e/actions/workflows/ci.yml/badge.svg)](https://github.com/joaovmgs/Gestor-NFS-e/actions/workflows/ci.yml)
[![Última versão](https://img.shields.io/github/v/release/joaovmgs/Gestor-NFS-e?display_name=tag)](https://github.com/joaovmgs/Gestor-NFS-e/releases/latest)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)

O Gestor NFS-e foi criado para contadores, escritórios de contabilidade e
empresas que precisam consultar notas emitidas e recebidas, baixar XML da NFS-e,
gerar o DANFSe em PDF e analisar retenções em uma planilha. Tudo funciona
localmente no Windows, sem login e sem enviar certificados ou documentos para
um servidor de terceiros.

## Download

Baixe o instalador mais recente na página de
[Releases](https://github.com/joaovmgs/Gestor-NFS-e/releases/latest).

1. Baixe `Gestor-NFSe-Setup-<versão>.exe`.
2. Execute o instalador.
3. Abra o Gestor NFS-e e cadastre a empresa.
4. Selecione um certificado A1 ou um certificado instalado no Windows.

> O instalador ainda não possui assinatura digital. O Windows SmartScreen pode
> solicitar confirmação antes da instalação.

## Recursos

- Consulta de NFS-e emitidas e recebidas no Ambiente de Dados Nacional.
- Sincronização automática e sequencial por NSU.
- Fila de consultas para trabalhar com várias empresas.
- Leitura de eventos e identificação de notas canceladas.
- Busca por número da nota, prestador, tomador ou valor.
- Filtros por período, tipo e situação da NFS-e.
- Download em ZIP separado por XML, PDF e notas canceladas.
- DANFSe em PDF baseado no modelo da Nota Técnica 008.
- Relatório XLSX com valores, retenções e situação das notas.
- Certificado A1 por arquivo `.pfx`/`.p12` ou repositório do Windows.
- Armazenamento opcional de credenciais protegido pelo Windows.
- Banco de dados SQLite local, sem painel administrativo ou serviço externo.

## DANFSe v2.0

O gerador de PDF deste projeto utiliza o layout **DANFSe v2.0** e foi
desenvolvido com base nas especificações da
[Nota Técnica nº 008 - Especificações Técnicas do DANFSe](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nt-008-se-cgnfse-danfse-20260505.pdf),
publicada pela SE/CGNFS-e.

Esta implementação ainda está em processo de homologação. Podem existir
alterações futuras na documentação oficial, diferenças pontuais de
posicionamento, espaçamento ou preenchimento de campos e pequenos erros de
layout. Antes de utilizar o PDF em processos fiscais ou operacionais críticos,
valide o resultado com os XMLs e requisitos aplicáveis.

## Como funciona

1. O aplicativo inicia uma API local disponível apenas em `127.0.0.1`.
2. O certificado selecionado autentica a consulta nos serviços nacionais da NFS-e.
3. Os documentos são consultados por NSU e armazenados no computador.
4. Novas consultas continuam do último NSU salvo e também verificam eventos.

Ao abrir uma empresa com certificado armazenado, o aplicativo verifica
automaticamente se existem novos documentos. Consultas adicionais entram em uma
fila para evitar excesso de requisições aos serviços da NFS-e.

## Dados e segurança

Configurações, referências de credenciais e o banco SQLite ficam em:

```text
%APPDATA%\nfse-desktop
```

Os XMLs e PDFs ficam na pasta escolhida pelo usuário. O padrão é:

```text
%USERPROFILE%\Documents\Gestor NFS-e
```

- A API local recebe um token aleatório a cada execução.
- Certificados e senhas armazenados são cifrados pelo `safeStorage` do Electron.
- Um certificado não armazenado é usado somente durante a consulta atual.
- Documentos fiscais, bancos e certificados são ignorados pelo Git.

Faça backup da pasta de dados antes de formatar ou trocar de computador.

## Requisitos para uso

- Windows 10 ou Windows 11, 64 bits.
- Certificado digital compatível com a consulta da NFS-e Nacional.
- Acesso à internet durante a sincronização.

O instalador inclui o backend e as dependências necessárias. Python, Node.js,
.NET e MSYS2 não são necessários no computador do usuário.

## Desenvolvimento

### Dependências

- Node.js 24 ou superior
- Python 3.12 ou superior
- .NET SDK 10 ou superior
- MSYS2/MinGW64 com Pango para gerar o instalador completo

### Executar localmente

```powershell
git clone git@github.com:joaovmgs/Gestor-NFS-e.git
cd Gestor-NFS-e
npm ci
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
npm run dev
```

### Verificar o projeto

```powershell
npm run lint
npm test
npm run build
```

### Gerar o instalador

```powershell
npm run dist:win
```

O instalador é criado em `release/Gestor-NFSe-Setup-<versão>.exe`.

## Estrutura

```text
src/                     Interface React
electron/                Processo principal, IPC, filas e credenciais
backend/src/nfse_desktop API local, SQLite, sincronização e exportação
backend/src/gov_nfse     Cliente da API Nacional e leitura dos XMLs
backend/src/danfse_brasil Geração do DANFSe
windows-cert-helper/     Integração com certificados do Windows
```

## Perguntas frequentes

### O aplicativo baixa XML de NFS-e em lote?

Sim. A exportação gera um ZIP com os XMLs e os DANFSe em PDF do período e tipo
selecionados.

### É possível consultar notas emitidas e recebidas?

Sim. As duas categorias são exibidas separadamente e possuem filtros próprios.

### O certificado e a senha são enviados para algum servidor?

Não. O aplicativo se conecta diretamente aos serviços nacionais da NFS-e. Os
dados persistidos permanecem no computador do usuário.

### Certificados instalados no Windows são compatíveis?

Sim. O helper nativo permite usar certificados disponíveis no repositório
pessoal do Windows, inclusive quando a chave privada não pode ser exportada.

### O projeto é oficial?

Não. Este é um projeto independente e não possui vínculo com a Receita Federal,
o Serpro ou os órgãos responsáveis pela NFS-e de padrão nacional.

## Contribuição

Issues e pull requests são bem-vindos. Não publique certificados, senhas, XMLs
reais, bancos de dados ou dados de contribuintes em issues ou commits.

## Licença

Distribuído sob a [licença MIT](LICENSE).
