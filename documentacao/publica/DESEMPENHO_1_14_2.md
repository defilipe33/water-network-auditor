# Desempenho e execução sob demanda — 1.14.2

Esta correção preserva o Quadro do Modelo, seus três fluxos e os mecanismos de análise e persistência. A investigação começou com medições da 1.14.1, antes de modificar os componentes de produção.

## Diagnóstico comprovado

O perfil com 18 fontes mostrou que uma troca de categoria executava a descrição de todas as fontes, resolvia repetidamente suas identidades e atualizava o resumo do Quadro três vezes. As sugestões de campos e a normalização de sinônimos também eram repetidas para pendências que não tinham mudado.

A nova interface herdava a construção completa da Central anterior e chamava sua atualização geral. Isso mantinha tabelas, preparação guiada e outros controles ocultos. A rotina periódica consultava o catálogo e reavaliava contexto mesmo quando Preparar estava em uso. O problema não dependia exclusivamente do número de feições.

O tema não foi identificado como uma rotina que reaplica o stylesheet a cada clique: ele já compara a assinatura da paleta. A construção, o polimento e o desenho de formulários Qt continuam tendo custo, especialmente na primeira abertura e no editor de atributos.

Não foram reproduzidos congelamentos longos nos cenários sintéticos. A repetição de trabalho foi confirmada por chamadas e perfis; isso não prova que explique todos os atrasos de um projeto operacional.

## Alterações

- A entrada utiliza a inicialização leve dos serviços da Central. Os controles antigos só são construídos ao abrir Ferramentas avançadas ou solicitar um acesso compatível específico. A mesma instância do cadastro e do índice de projetos é compartilhada.
- O timer da Central legada permanece parado. Quando o contexto muda e ela está visível, recebe atualização; durante a navegação comum não é atualizada.
- A troca de categoria atualiza seu painel e o resumo uma vez. A validação completa das fontes fica nas mudanças de dados, carregamento e ações explícitas.
- O estado das pendências é reutilizado enquanto categoria, esquema, mapeamento, filtro, resultados, conflitos e avisos forem os mesmos. Uma troca de projeto limpa esse estado.
- Sinais de alteração de campos, dados, fonte, CRS e filtro do provedor das fontes cadastradas invalidam a conferência e agendam uma atualização única. Se uma atualização já ocorrer, o agendamento pendente é cancelado. Edições em camadas alheias ao cadastro não invalidam a conferência.
- A resolução de fonte utiliza o ID da camada como atalho somente depois de conferir provedor e identidade. O caminho conservador continua disponível para fontes relocalizadas ou ambíguas.
- O catálogo é consultado quando necessário para trabalhos/cenários, com invalidação por tamanho e timestamp do SQLite e WAL. Listas e seletores inalterados não são reconstruídos.
- O contexto técnico é reavaliado quando muda sua identidade/estado ou a marca da base. Ao executar uma ferramenta, os requisitos são conferidos novamente. As verificações de integridade e identidade na abertura foram preservadas.
- O carregamento do painel integrado e de suas saídas especializadas foi adiado até a utilização. Os módulos de formulários Qt cuja importação tardia provocou falha nativa nos testes mantiveram a importação anterior. Suas janelas continuam sendo instanciadas somente quando solicitadas.

As propriedades adicionais do editor são construídas somente ao expandir a seção ou solicitar um controle por API. Seus mapeamentos e valores iniciais são preservados mesmo quando a seção não é aberta.

Nenhum módulo inteiro foi removido. Foram retiradas chamadas duplicadas e a atualização automática dos controles ocultos. Não houve alteração de algoritmos geométricos, hidráulicos, de grafos, de CRS ou de versionamento.

## Classificação arquitetural

| Grupo | Tratamento |
| --- | --- |
| A — preservar | Leitor WaterGEMS, cenários, Active Topology, grafos, auditoria, persistência, validação espacial, catálogo, histórico, conjuntos e exportações continuam com seus contratos. |
| B — sob demanda | Central visual legada, preparação guiada antiga, visualizadores de investigação, relatórios e exportações especializadas. A janela GIS existente e as importações Qt necessárias à estabilidade foram mantidas. |
| C — comprovadamente redundante | Duas atualizações extras do resumo por troca; descrição completa das fontes na seleção de categoria; chamada geral da Central oculta. Essas execuções foram eliminadas; seus serviços continuam disponíveis onde necessários. |

## Método de medição

Foram usados os ZIPs instalados em perfis isolados no QGIS 3.44.15, Windows 64 bits, Python 3.12.15, arquitetura AMD64 e 16 processadores lógicos informados pelo ambiente. Não foi obtida uma medição confiável de RAM/working set nem de I/O físico. Esses dados não são inferidos da redução de widgets.

Os contextos são:

| Cenário | Conteúdo |
| --- | --- |
| A | Projeto vazio, sem fontes ou WaterGEMS ativo. |
| B | 18 fontes sintéticas em memória, 66.600 feições: 6 redes, 4 equipamentos, 4 áreas e 4 fontes de nós, com tamanhos de 100, 1.000 e 10.000 feições. |
| C | O conjunto B com revisão persistida do Modelo GIS, investigação/proposta em GeoPackage e duas bases topológicas sintéticas dos cenários 1 e 2. |

A comparação nativa final foi realizada em 19/11/2026, sequencialmente, após encerrar a suíte automatizada. As mesmas operações e parâmetros foram usados nas duas versões. Houve 15 repetições das navegações, cinco dos ciclos de formulário, apresentação e histórico, três das trocas de projeto/cenário e uma amostra de cada abertura inicial. A mediana quente exclui a primeira amostra; p95 e pior caso incluem todas. Com poucas repetições, p95 pode coincidir com o pior caso.

A instrumentação registra perf_counter, chamadas e tempos inclusivos de funções, thread principal/worker, aberturas SQLite, pedidos de feições, acessos a metadados, chamadas de filesystem e variação líquida de widgets por identidade C++. Isso não representa cada instrução SQL, I/O físico ou operação interna C++ do provedor. O cProfile foi gravado em arquivos locais. Tempos inclusivos não devem ser somados como custos independentes.

A execução nativa processa eventos Qt entre as ações. O timer periódico do Auditor é parado durante a medição isolada das operações; sua atualização é medida separadamente. A resolução dos timers do Windows e o polimento/pintura Qt impõem variação. O sistema operacional, caches de arquivos e demais aplicações não foram reinicializados entre amostras. Os números são referências desta bancada, sem garantia universal.

O contador de widgets informa aumento líquido ao fim da operação, não cada objeto transitório criado e destruído. Ao abrir a interface no cenário B, passou de 396 para 220 widgets nos dois temas. O ciclo editor mede **abrir e cancelar**, com construção/destruição e atualização posterior; não é uma medida isolada de um clique em Abrir campos. O destaque mede o envio da solicitação; a espera pelo worker é conferida separadamente, fora desse tempo.

## Resultados comparativos

### Primeira abertura da interface (uma amostra por contexto, ms)

| Tema | Cenário | 1.14.1 | 1.14.2 |
| --- | --- | ---: | ---: |
| escuro | A_vazio | 347.1 | 114.7 |
| escuro | B_multifonte | 349.4 | 116.6 |
| escuro | C_integrado | 456.3 | 128.3 |
| claro | A_vazio | 267.0 | 114.9 |
| claro | B_multifonte | 289.6 | 155.8 |
| claro | C_integrado | 339.9 | 138.8 |

### Navegação no cenário integrado (ms)

| Tema | Operação | Mediana antes | Mediana depois | p95 antes | p95 depois |
| --- | --- | ---: | ---: | ---: | ---: |
| escuro | Preparar | 16.0 | 3.0 | 52.9 | 23.3 |
| escuro | Quatro categorias, ciclo | 54.9 | 21.0 | 82.2 | 49.0 |
| escuro | Investigar | 7.0 | 7.0 | 31.8 | 16.0 |
| escuro | Meus trabalhos | 8.1 | 8.0 | 32.9 | 47.1 |
| escuro | Selecionar fonte | 3.0 | 3.0 | 31.5 | 13.0 |
| escuro | Painel/janela, ida e volta | 90.8 | 86.7 | 102.7 | 115.1 |
| escuro | Reabrir a mesma janela | 16.0 | 11.1 | 29.0 | 22.9 |
| escuro | Consultar histórico | 15.4 | 16.2 | 96.6 | 71.3 |
| escuro | Projetos, ida e volta | 68.6 | 38.7 | 72.3 | 47.1 |
| escuro | Cenários, ida e volta | 93.6 | 67.7 | 127.4 | 95.2 |
| escuro | Editor: construir e cancelar | 250.3 | 121.0 | 252.5 | 135.0 |
| claro | Preparar | 12.0 | 3.0 | 37.4 | 27.5 |
| claro | Quatro categorias, ciclo | 73.8 | 23.4 | 119.0 | 50.3 |
| claro | Investigar | 8.0 | 8.0 | 32.8 | 31.3 |
| claro | Meus trabalhos | 9.1 | 8.0 | 46.7 | 42.5 |
| claro | Selecionar fonte | 3.0 | 3.0 | 37.2 | 48.4 |
| claro | Painel/janela, ida e volta | 118.8 | 107.6 | 133.9 | 124.5 |
| claro | Reabrir a mesma janela | 21.3 | 14.4 | 56.1 | 51.5 |
| claro | Consultar histórico | 15.8 | 15.1 | 70.4 | 95.9 |
| claro | Projetos, ida e volta | 87.8 | 52.8 | 92.5 | 58.3 |
| claro | Cenários, ida e volta | 135.5 | 105.6 | 173.3 | 145.6 |
| claro | Editor: construir e cancelar | 226.7 | 124.5 | 240.7 | 138.2 |

### Trabalho eliminado

As duas primeiras linhas correspondem a 15 seleções de Redes no cenário B; as duas últimas, a cinco atualizações gerais.

| Contador | Antes | Depois |
| --- | ---: | ---: |
| Descrições de fontes | 270 | 0 |
| Resumos do Quadro | 45 | 15 |
| Atualizações da Central legada | 5 | 0 |
| Aberturas SQLite | 20 | 0 |

### Metas de referência

As metas aplicam-se às interações quentes. O ciclo de quatro categorias e a ida/volta de apresentação são operações compostas. Verifique o JSON para operações individuais, pior caso e amostras iniciais. Nem os valores nem o contador de widgets representam uma garantia de desempenho em outro computador.

As métricas completas, inclusive primeira amostra, mediana, p95, pior caso e contadores por operação, estão no [JSON sintético revisado](metricas/desempenho_1_14_2.json). Os arquivos brutos de perfil e bases de ensaio permanecem locais.

## Cache e exatidão

Não há cache de resultados hidráulicos nem transferência de conclusões. Os caches são da apresentação. Projeto, cenário, base, perspectiva, filtros e identidade das fontes continuam distinguíveis.

As alterações feitas através do QGIS invalidam os dados dependentes por sinais. Para modificações externas que ainda não tenham sido comunicadas pelo provedor, utilize Conferir fontes/recarregar; as ações técnicas continuam fazendo suas próprias verificações. A marca de arquivo é uma pista de mudança, não comprovação de equivalência técnica. Não se usa o nome para substituir uma identidade.

Os destaques continuam usando snapshots e workers existentes, com limite de 500 feições, sem alterar seleções, fontes, renderers ou árvore para cada clique. Nenhuma rotina geométrica pesada nova foi colocada no thread principal.

## Diagnóstico opcional

O módulo `auditoria_aplicacao.diagnostico` não é importado pela operação normal. Com o complemento aberto, sem formulário em edição e fora de processamento, ele pode ser usado no console do QGIS em uma sessão de teste:

```python
from pathlib import Path
import qgis.utils
from auditoria_aplicacao.diagnostico import Diagnostico
app = qgis.utils.plugins['auditoria_redes'].app
sonda = Diagnostico(Path(app.catalogo.raiz) / 'diagnostico_interface')
sonda.envolver(app.central.quadro, 'escolher', 'categoria')
sonda.envolver(app.catalogo, 'listar_opcional', 'catalogo')
sonda.medir('ciclo_categorias', lambda: [
    app.central.quadro.escolher(g)
    for g in ('REDES', 'EQUIPAMENTOS', 'ÁREAS', 'CONECTIVIDADE')
], repeticoes=15)
sonda.salvar()
sonda.fechar()
```

`perfil('nome', acao)` grava um cProfile local. `fechar()` restaura os métodos instrumentados; use antes de descarregar o complemento. `Diagnostico(..., habilitado=False)` não instala sondas nem grava arquivos. A sonda não registra argumentos, SQL ou URIs. Utilize nomes de operações genéricos. Perfis e diagnósticos brutos devem permanecer locais, pois podem conter caminhos do ambiente.

## Regressões, instalação e aceitação

A suíte completa aprovou 1.320 testes em 39 módulos: os 1.304 existentes e 16 novos. Duas regressões existentes passaram a fornecer o catálogo pela interface de leitura, em vez de depender da atribuição direta de um atributo interno, preservando as mesmas verificações de projeto/cenário e exclusão de backups.

O pacote final foi exercitado novamente em processos de criação e reabertura com fontes em disco, sete associações GIS, rascunho, revisões, mapa e proposta persistida. O encerramento só é considerado bem-sucedido com sucesso, aboutToQuit e retorno zero. O ensaio é automação Qt em QGIS Desktop com revisão de capturas; não é aceitação humana nem teste físico de dois monitores.

Instale o ZIP 1.14.2 pelo gerenciador de complementos e reinicie o QGIS. A 1.14.1 permanece disponível para comparação e retorno. Em seu projeto, repita: abrir, alternar rapidamente grupos, editar/salvar, destacar, mudar painel/janela, consultar trabalhos, trocar projeto/cenário com e sem rascunho e reiniciar. Nenhuma informação original deve mudar.

## Capturas

Capturas reais dos processos instalados, usando exclusivamente dados sintéticos. A composição visual foi preservada; a mudança principal desta correção é o custo da execução.

| Contexto | 1.14.1 | 1.14.2 |
| --- | --- | --- |
| Escuro, multifonte | [Antes](capturas/desempenho/antes_escuro.png) | [Depois](capturas/desempenho/depois_escuro.png) |
| Claro, multifonte | [Antes](capturas/desempenho/antes_claro.png) | [Depois](capturas/desempenho/depois_claro.png) |

[Projeto vazio](capturas/desempenho/vazio.png) · [Destaque real no mapa](capturas/desempenho/mapa.png) · [Painel estreito com rascunho](capturas/desempenho/estreito.png) · [Janela independente com o mesmo rascunho](capturas/desempenho/independente.png) · [Cadastro reaberto em outro processo](capturas/desempenho/reabertura.png).

As imagens foram inspecionadas quanto a legibilidade, contexto e ausência de dados operacionais. No painel estreito, nomes extensos do seletor são abreviados; o editor mantém rolagem. A área de mapa muda conforme a largura do painel. A avaliação não constitui teste humano físico em dois monitores.

## Limitações e próximos ensaios

A bancada não reproduziu o atraso operacional prolongado informado pelo usuário. As trocas de categorias tiveram menos trabalho e melhores resultados em vários contextos, enquanto o p95 de algumas operações, como Meus trabalhos no escuro e histórico no claro, aumentou. Aberturas e formulários continuam sujeitos a variação. Os casos desfavoráveis estão nas tabelas e no JSON.

A primeira construção/pintura de widgets e o ciclo de editor ainda têm custo; não foi feita uma reescrita desse formulário. Leituras iniciais de bases grandes e verificações de integridade podem custar mais que as bases sintéticas. Uma medição com o projeto operacional, mantendo o log local, continua necessária para identificar efeitos de provedores remotos, discos e tamanho de GeoPackages. Não se afirma que todos os atrasos possíveis foram eliminados.

O comportamento de temas da 1.14.1 foi preservado, inclusive a limitação do QGIS ao retornar diretamente a default sem repor toda a paleta; reinicie quando necessário. Nenhum requisito administrativo, confirmação repetitiva ou nova ferramenta de modelagem foi acrescentado.
