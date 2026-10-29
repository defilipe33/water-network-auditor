# Arquitetura topológica WaterGEMS

Na 1.4.0, `janelas.py` centraliza recuperação e propriedade visual; `atividade.py`
reutiliza `Trabalho` e integra indicadores, checkpoints e ciclo de vida dos workers.
Leitura de investigação e comparação de bases executam cálculo em segundo plano;
publicação de camadas permanece na GUI. Os algoritmos não foram reescritos. Veja
[arquitetura, cobertura por operação e limites](JANELAS_E_ATIVIDADES.md).

Na 1.3.1, o bloqueador do complemento implementa `allowExit()` e delega ao controlador.
`abrir_diagnosticos(..., gerenciar_saida=False)` evita um segundo registro no fluxo
gerenciado. O padrão independente mantém a guarda para uso pelo console. O descarte
espacial é consumido antes dos eventos de fechamento; referências fracas, verificação
de objetos destruídos e cancelamento do registro protegem o ciclo de vida Qt.
Detalhes e limites: [estabilidade e finalização](ESTABILIDADE_E_FINALIZACAO.md).

Na 1.3.0, `organizacao_camadas.py` centraliza grupos por contexto e reutilização de
representações próprias. `decisoes.py` acrescenta registros leves em `IGD_REGISTROS`
sem converter o histórico anterior. O formulário simplifica o uso cotidiano e conserva
as validações de confirmação. Guia: [investigação e camadas](FLUXO_INVESTIGATIVO.md).

`indice_bases.py` centraliza a verificação idempotente do esquema, migração, backup
e erros de acesso do catálogo operacional. `gerenciamento.Catalogo` conserva sua API
e reconstrói o índice a partir das identidades internas das bases. Operações opcionais
de indexação não impedem consulta de uma base ativa válida. GeoPackages, extrator e
algoritmos não são modificados por esse mecanismo. Consulte [recuperação](RECUPERACAO_CATALOGO.md).

`deteccao_espacial.py` complementa `referencia_espacial.py` com leitura de declarações,
inventário GIS, ranking cadastral, estatísticas e controles pontuais. O assistente
`auditoria_aplicacao/assistente_espacial.py` executa tarefas em QThread e utiliza a
persistência existente. `bases.py` conserva metadados do snapshot e adiciona
`WB_EVIDENCIA` somente às novas bases com validação. O comparador recebeu um callback
opcional de cancelamento; seus critérios geométricos foram preservados. Consulte
[critérios, arquitetura da evidência e limitações](VALIDACAO_ESPACIAL.md).

O [fluxo de referência espacial e inspeção tabular](USABILIDADE_CRS.md) complementa
esta arquitetura. `referencia_espacial.py` valida evidências por contexto e grava a
confirmação em nova versão através da persistência existente. Não modifica o leitor,
o resolvedor ou o grafo. `inspecao_tabular.py` projeta os vínculos para consulta sem
eliminar candidatos, valores brutos ou relações técnicas.

`scripts/auditoria_topologica_watergems` separa leitura, resolução, grafo, geometria,
investigação, persistência, diagnóstico e saídas. Não exige que o WaterGEMS esteja aberto.

`leitura.Banco` abre SQLite somente leitura, identifica o modelo pelo GUID, resolve
herança de cenários e alternativas e mantém proveniência dos valores. Geometria,
topologia, Active Topology, propriedades e Initial Settings têm contextos distintos.
Nulo explícito não é substituído arbitrariamente por um registro de outra alternativa.

`resolucao.py` prioriza Start/Stop explícitos. Um directed node proprietário único
de Downstream pode suprir apenas Start ausente em condições conservadoras; referência
preenchida, inválida ou contraditória não é encoberta por coincidência geométrica.
Jusante ausente, link inexistente, excluído, inativo e ambíguo são diagnósticos distintos.

`topologia.py` usa grafo NetworkX. ESTRUTURAL representa relações cadastradas,
inclusive elementos inativos identificados. TODAS_VALVULAS_ABERTAS respeita Active
Topology, direcionalidade das retenções e bloqueio de bombas sem estado comprovado.
ESTADOS_DO_CENARIO permanece indisponível. Estados iniciais não demonstram operação
ao longo de uma simulação. Componentes fracos e alcance dirigido têm significados distintos.

Elementos sem fonte no grafo não são automaticamente redes sem abastecimento real.
Reservatórios, tanques e bombas são diferenciados; bomba não é fonte de água.
Dispositivos intermediários e incidências fazem parte da interpretação do grafo.

`espacial.py` só permite medições em metros com CRS e unidade confirmados. Não
deduz um EPSG pela localização presumida. Hipóteses espaciais ficam identificadas
como hipóteses; não acrescentam arestas ao grafo validado.

`bases.py` acrescenta WB_BASE, WB_ELEMENTOS e WB_RESULTADOS ao GPKG existente,
conservando dados brutos relevantes e resultados de ambas as perspectivas.
`gerenciamento.py` coordena catálogo, sugestões de nomes e integração gerenciada.
Metadados e páginas do inventário podem ser lidos sem reconstruir todo o modelo.

O snapshot não representa todos os dados hidráulicos ou de simulação do WaterGEMS.
A reconstrução confronta conexões, componentes, resumos e diagnósticos persistidos.
O original pode estar indisponível; divergências semânticas bloqueiam reprodução indevida.

O Model Builder Composer é referência externa de validação; não é dependência
runtime nem código incorporado. Ver [atribuições](../../THIRD_PARTY_NOTICES.md).


## Locais manuais e conjuntos — 1.6.0

Extensão aditiva IGD com geometrias históricas e visão de locais ativos, associações manuais, recuperação transacional e conjuntos por critérios cadastrais/estruturais. Guia: LOCAIS_MANUAIS_E_REDES.md


## Corredores e recuperação — 1.7.0

Métodos separados, Junctions como terminais, rotas compartilhadas e consulta por UUID/perspectiva de todas as análises persistidas. Guia e limitações: CORREDORES_E_RECUPERACAO.md


## Exportação, catálogo e relatórios — 1.8.0

Corredores completos, Queries, gestão reversível e relatório ilustrado offline.
[Guia, privacidade, requisitos e roteiro de validação](EXPORTACAO_CATALOGO_RELATORIOS.md).

## Acompanhamento e apresentação — 1.8.1

`acompanhamento.py` estende a persistência IGD no mesmo GeoPackage: esquema v1, backup completo verificado, gravação transacional com controle otimista, histórico imutável e assinatura do contexto local para reavaliação. Não substitui análises técnicas. `fontes_relatorio.py` centraliza identificação local/remota e permissões antes de renderizar. Relatórios e Queries reutilizam os exportadores existentes. [Estrutura, regras e limitações](RELATORIOS_QUERIES_ACOMPANHAMENTO.md).

## Restrições nos corredores — 1.9.0

`restricoes_percurso.py` prepara sobreposição investigativa dirigida e visão filtrada; o Dijkstra existente recebe custos lexicográficos opcionais, conservando seu comportamento sem restrições. `restricoes_ui.py` reutiliza seleção tabular/cartográfica e perfis em IGD_OBJETOS/IGD_OBJ_HIST, sem infraestrutura paralela. Exportação reconstrói o mesmo grafo de trabalho e conserva o perfil/regra. [Contrato, restrições obrigatórias, persistência e aceitação](RESTRICOES_CORREDORES.md).


## Ilhas sem origem — 1.10.0

Busca multiorigem no grafo completo; estrutural fraca e restrita dirigida separadas. Extensão relacional IGD_ILHAS com backup, cache e histórico de análises; decisões, RESOLVIDO e comparações reutilizam a persistência existente. Sem origens: inconclusivo. Tanks somente como hipótese explícita. Demanda não validada permanece indeterminada. Guia público: [ILHAS_SEM_ORIGEM](./ILHAS_SEM_ORIGEM.md).
