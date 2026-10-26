# Arquitetura topológica WaterGEMS

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
