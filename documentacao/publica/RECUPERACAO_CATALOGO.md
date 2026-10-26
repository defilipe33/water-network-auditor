# Recuperação do catálogo — versão 1.2.1

`catalogo_bases.sqlite` é um índice operacional da pasta de trabalho. Os GeoPackages
continuam sendo as fontes persistentes de eventos, versões, decisões, propostas e históricos.

## Defeito e causa demonstrada

Na versão anterior, a tabela `bases` era criada somente no construtor de `Catalogo`.
Operações posteriores abriam SQLite sem verificar essa condição. `sqlite3.connect`
pode criar um arquivo vazio se o arquivo desaparecer durante a sessão; a consulta
`SELECT ... FROM bases` falhava. Um arquivo truncado/substituído após a construção
produzia o mesmo resultado. A abertura do assistente propagava a exceção sem tratamento.

Essa sequência foi reproduzida. A existência de um arquivo vazio, isoladamente, não
identifica o que o criou ou truncou na sessão original. Não foi demonstrado defeito
no WaterGEMS, no CRS ou nos GeoPackages. O fechamento da conexão no construtor antigo
não prova falta de commit do DDL; a falha era depender da inicialização uma única vez.

## Comportamento atual

| Situação | Tratamento |
|---|---|
| Ausente ou zero bytes | Inicialização transacional do esquema na pasta selecionada |
| SQLite válido sem `bases` | Backup quando há outras tabelas; criação sem removê-las |
| Esquema antigo | Backup SQLite íntegro, migração transacional e tabela legada preservada |
| Registro legado incompleto/duplicado | Conservado na tabela legada e sinalizado |
| JSON de registro inválido | Registro não apagado; advertência, sem interpretar como base válida |
| Arquivo movido | Referência antiga conservada; relocalização exige UUID/tipo correspondentes |
| Índice desatualizado | Advertência; Reexaminar pasta atualiza metadados das bases reconhecidas |
| Mesmo UUID/tipo e cópias byte a byte iguais | Uma opção de versão, com caminhos alternativos conservados |
| Mesmo UUID/tipo, conteúdos diferentes | Opções preservadas e conflito sinalizado; sem escolha automática |
| Corrupção real | Não é tratada como vazio; arquivo não apagado nem substituído |
| Bloqueio/permissão | Mensagem orientativa; possibilidade de tentar novamente |

Toda operação verifica o esquema. Uma leitura de catálogo válido não exige escrita.
Criação e migração usam transação com `BEGIN IMMEDIATE`; sessões concorrentes não
publicam um esquema intermediário. A pasta é vinculada à instância; não há alternativa
silenciosa para o diretório atual. Se desaparecer ou mudar de destino, a operação é bloqueada.

O catálogo vazio/recuperado reexamina os GeoPackages publicados no diretório do projeto.
As identidades vêm de `WB_BASE`, `IG_EXECUCOES` ou `EXECUCOES`, nunca do nome do arquivo.
Diretórios técnicos/intermediários não são indexados automaticamente; um arquivo técnico
reconhecido pode ser adicionado explicitamente pelo seletor, se necessário.

O assistente trata a indisponibilidade do índice separadamente da base ativa. Mostra
advertências e permite analisar a base topológica ativa íntegra, mesmo se o catálogo
precisar de reconstrução. Falhas inesperadas na construção recebem mensagem controlada.
O seletor também verifica se o arquivo ainda contém a identidade escolhida antes de abri-lo.

## Atualização

1. Feche as janelas da auditoria e o QGIS.
2. Instale o ZIP 1.2.1 pelo gerenciador de complementos e reinicie o QGIS para evitar
   módulos antigos mantidos em memória. Preserve as pastas e bases existentes.
3. Escolha a mesma pasta de trabalho. Não apague manualmente o catálogo vazio.
4. Abra a auditoria e a base WaterGEMS e clique em **VALIDAR REFERÊNCIA ESPACIAL DO WATERGEMS**.
5. Confira as advertências e as bases recuperadas. Use **Reexaminar pasta** ou **Adicionar
   arquivo** para referências não localizadas; confira UUID e versão.

Se houver corrupção real, preserve o arquivo, restaure um backup íntegro ou escolha
explicitamente outra pasta para reconstruir o índice e adicionar as bases. A versão
1.2.1 não substitui automaticamente um catálogo corrompido. Histórico e revisões dos
GeoPackages não são regravados pela reconstrução do índice.

## Roteiro de validação

- Catálogo inexistente, vazio, válido, antigo, corrompido e somente leitura.
- Arquivo removido/truncado depois da inicialização do complemento.
- Duas sessões gravando o mesmo índice e recuperação após bloqueio/interrupção.
- Reconstrução, arquivo movido, cópias idênticas e conflitos de conteúdo.
- Assistente com base ativa válida e índice indisponível; mensagem sem traceback.
- Instalação do ZIP em perfil isolado, abertura do assistente e reabertura em outra
  sessão, conferindo identidades e quantidades da sessão testada.

Testes Qt offscreen, ensaios pela API Qt no desktop e aceitação manual por cliques
são evidências diferentes. Dados e arquivos operacionais dos ensaios ficam fora do GitHub.

## Resultados da entrega

No QGIS 3.44.15/Python 3.12, passaram **562 testes**: os 532 anteriores e 30 novos,
em 239,132 s. O conjunto cobre também arquivo somente leitura no Windows, bloqueio
real SQLite, falha de backup/migração, sessões concorrentes e pasta não informada.

O ZIP foi instalado pelo gerenciador oficial em perfil isolado, com escala Qt 150%.
O catálogo foi zerado após a inicialização e o assistente abriu e concluiu a detecção.
Outra sessão recuperou as bases com as mesmas identidades. Os GeoPackages da sessão
fornecida permaneceram iguais por hash, incluindo seus registros de revisão/histórico.
As contagens da sessão recebida foram utilizadas sem impor a referência histórica.

Esses ensaios foram conduzidos pela API Qt. Aceitação humana por cliques e encerramento
normal do processo permanecem pendentes: os dois processos desktop excederam o prazo de
encerramento do ensaio, apesar de concluírem as etapas verificadas.
