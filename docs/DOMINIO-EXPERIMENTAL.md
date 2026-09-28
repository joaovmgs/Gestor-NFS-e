# Integração experimental com Domínio

Ative **Organização de pastas para o Domínio** nas configurações. O formulário
solicita driver ODBC, servidor, banco de dados, usuário, senha e host (endereço:porta).
O computador precisa alcançar a rede do banco, diretamente ou por VPN, e ter o
driver SQL Anywhere de 64 bits instalado.

**Conectar e salvar acesso** valida a conexão e busca CNPJ, código e apelido em
`bethadba.geempre`, somente para leitura. O usuário SQL precisa de acesso a essa
tabela. As credenciais são criptografadas pelo Electron safeStorage, vinculadas
ao usuário do Windows; a senha salva nunca é enviada de volta à interface.
Deixe a senha vazia ao editar para manter a existente.

Cada empresa é associada pelo CNPJ completo, incluindo a filial. Cadastros
ausentes, ambíguos ou com apelidos incompatíveis com nomes de pasta são exibidos
para revisão. Sem vínculo, seus XMLs usam `XX-EMPRESA-CNPJ`, mantendo as pastas
Emitidas/Recebidas e o mês. Os vínculos são consultados ao abrir o aplicativo,
ao cadastrar uma nova empresa ou ao conectar manualmente nas configurações.
Não há consultas periódicas ao banco, nem uma sessão SQL permanentemente aberta.
Se a consulta falhar, os vínculos anteriores permanecem em uso; empresas ainda
sem vínculo usam o padrão provisório. Quando uma consulta encontrar o cadastro,
os XMLs das pastas provisórias serão reorganizados automaticamente, com atualização
dos caminhos no banco local. Demais pastas existentes são reorganizadas somente
pela opção da empresa. A interface mostra falhas, sem aviso permanente de sucesso.

Novos XMLs vinculados são gravados em:

```text
Pasta das notas/
  Emitidas/Código-Apelido/MMAAAA/arquivo.xml
  Recebidas/Código-Apelido/MMAAAA/arquivo.xml
```

No Domínio, configure duas rotinas e selecione a pasta `Emitidas` ou `Recebidas`
como raiz de cada uma. Use a opção de buscar a pasta da competência da execução.
Os nomes dessas duas raízes são uma escolha do Gestor; o trecho
`Código-Apelido/MMAAAA` segue a organização documentada pelo Domínio. O mês é
o da emissão do XML, conforme a opção experimental já existente.

Referência: [Perguntas e respostas sobre rotinas automáticas](https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=5516).

Em **Configurações da empresa**, código e apelido são exibidos para consulta
enquanto o modo está ativo. **Reorganizar XMLs existentes** aplica o cadastro
atual do banco e separa as direções. A cópia é registrada no banco local antes
de remover o original; arquivos de conteúdo diferente no destino geram um erro
sem sobrescrita. Eventos e exportações ZIP não usam esse leiaute de pastas.
