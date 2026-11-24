# Relatório técnico — Water Network Auditor 1.15.2

Data de consolidação: 24/11/2026. Escopo: interpretação, relevância e apresentação dos resultados geométricos existentes. [Guia das regras e operação](RELEVANCIA_GIS_1_15_2.md). [Arquitetura da próxima etapa](ROADMAP_GIS_ELEMENTOS_COMPLEMENTARES.md).

## Diagnóstico e correção

A fila da 1.15.1 apresentava contatos com fronteiras e continuidades candidatas sem uma classificação independente de relevância. Isso favorecia a leitura de qualquer ponto como problema. O motor não dizia que uma travessia era defeito hidráulico; faltava explicitar essa diferença na apresentação e na organização da fila.

Confirmou-se também que COINCIDENCIA é coincidência entre tubo e fronteira poligonal, EXTREMIDADE representa ausência de uma amostra do lado da ponta da linha e o ponto de continuidade é representativo do par de extremidades. Nenhum desses fatos comprova conectividade ou desabastecimento.

A 1.15.2 acrescenta regras reproduzíveis, motivo por evento, contagens, fila inicial de atenção e filtros combinados. O índice preserva o UUID e as relações existentes, sem recalcular a auditoria. Classificação geométrica, relevância e acompanhamento continuam separados. A consulta opcional de equipamentos distingue proximidade de associação declarada e recusa distância em graus.

O mapa recebeu quatro símbolos por relevância, consulta por seleção do ponto e destaque temporário dos elementos. Estilos personalizados existentes são preservados, inclusive quando o usuário apenas altera a cor de uma categoria. Projetos antigos não são migrados para registrar essa interpretação; a versão da regra aparece na tela e nas exportações.

Durante os ensaios desktop, o OGR emitiu mensagens ao gravar o QGZ com um subset de execução desnecessário nas duas camadas de resultados. O ensaio comparativo sem subset não emitiu as mensagens. A correção consulta somente o índice de execuções e aplica subset quando a base contém outras execuções. A separação de bases compartilhadas permanece coberta por regressão. Não se atribui esse comportamento a perda de dados ou ao encerramento do complemento.

Uma execução também registrou mensagem transitória de leitura OGR durante a primeira gravação individual. A verificação de integridade SQLite retornou `ok`. A gravação passou a aguardar o término da renderização, preservar o estado de congelamento dos canvases e recarregar os provedores próprios antes de restaurá-los. O worker e as transações existentes foram mantidos. Regressões cobrem restauração no sucesso, na falha e com mapa previamente congelado.

## Código reaproveitado e arquivos

O núcleo geométrico, o agrupador, os vínculos persistidos, o mecanismo de revisões, o controle de concorrência, o leitor WaterGEMS, os workers e o Quadro do Modelo foram mantidos. Nenhum algoritmo hidráulico ou de construção de topologia foi acrescentado.

Novos módulos: `relevancia_gis.py`, `contexto_equipamentos_gis.py`, `mapa_relevancia_gis.py`.

Alterações de integração: `analise_gis_ui.py`, `painel_investigacao_gis.py`, `investigacao_gis.py`, `analise_modelo_gis.py`, `mapa_fontes.py`, `exportacao_investigacao_gis.py` e metadata do complemento. Documentação, README e catálogo de hashes das capturas foram atualizados.

Testes: `test_relevancia_gis.py`; a fixture de `test_integracao_modelo_gis.py` passou a escolher explicitamente Todas as ocorrências para continuar exercitando decisões sobre travessias informativas. Nenhum teste anterior foi removido.

## Testes automatizados

A suíte completa executou **1.471 testes em 43 módulos**, todos aprovados, em 607,81 s. Após as proteções de CRS, o índice de associações e a coordenação de gravação/renderização, os três módulos afetados foram revalidados: **31 + 40 + 44 = 115 testes**, todos aprovados, com processos de código 0. Total consolidado: **1.476 testes distintos**, mantendo os **1.432 testes anteriores**.

Cobertura adicional: travessias em contextos de setor/VRP/booster, contato com fronteira, continuidade candidata, ambiguidade, classe desconhecida, ausência de vínculos, referência ausente, independência da situação, grupos mistos, contagens e filtros, seleção de ponto por UUID, estilo virtual e personalizado, base compartilhada, associações declaradas afastadas, consulta/invalidade do contexto de equipamentos, CRS em graus, exportação integral, histórico antigo e construção do índice em worker.

Ocorreram falhas nas primeiras execuções de desenvolvimento: uso de um ícone de RubberBand inexistente, API incorreta no teste de cor e referência temporária de símbolo no teste. Foram corrigidas e reexecutadas. O teste de cor agora retém os objetos de categoria enquanto clona o símbolo, respeitando seu ciclo de vida. As execuções iniciais com falha não foram contabilizadas como aprovadas.

## QGIS Desktop instalado

Ambiente: **QGIS 3.44.15-Solothurn**, **Python 3.12.15**, **Windows 11**, perfil isolado, ZIP realmente extraído e carregado por sua `_biblioteca`. Os cinco cenários usam dados sintéticos:

| Ensaio | Verificações |
|---|---|
| Escuro | GIS independente, fila de revisão, informativas, ponto selecionado, geometrias, filtros, decisões, histórico, exportações, painel estreito e janela |
| Claro | Mesmo fluxo, com apresentação clara |
| Reabrir | Recuperação de decisão individual em nova sessão/processo |
| Legado | Cópia de trabalho sintético da 1.15.0, recuperação de geometrias por assinatura e hash da base anterior preservado |
| WaterGEMS associado | Base topológica sintética persistida, contexto/cenário associado, investigação GIS, consulta de equipamentos, legenda e fonte SQLite preservada |

Na amostra principal, **5 eventos / 4 locais**: **4 Informativos**, **1 Revisar**, **0 Inconsistências identificadas**, **0 Indeterminados**. Uma decisão individual Verificado convive com acompanhamento Misto do agrupamento. Três revisões de agrupamento foram mantidas. Exportações SHP/CSV e GPKG incluem os eventos informativos, mesmo fora da fila inicial.

Cada processo deve retornar código 0, registrar `aboutToQuit` e sair dentro do prazo; timeout não é aprovação. O QGZ salvo é reaberto e suas camadas/atributo de relevância são conferidos. Os hashes das fontes são comparados antes/depois. As capturas são reais, inspecionadas e contêm somente dados sintéticos.

## Capturas

| Evidência | Imagem |
|---|---|
| Fila inicial e contagens | [Escuro](capturas/relevancia_gis_1_15_2/fila_revisao_escuro.png) |
| Continuidade candidata / mapa | [Evento a revisar](capturas/relevancia_gis_1_15_2/continuidade_revisar.png) |
| Seleção do ponto por UUID | [Mapa e detalhes](capturas/relevancia_gis_1_15_2/ponto_selecionado.png) |
| Travessia informativa | [Escuro](capturas/relevancia_gis_1_15_2/informativa_escuro.png), [claro](capturas/relevancia_gis_1_15_2/informativa_claro.png) |
| Histórico | [Revisões preservadas](capturas/relevancia_gis_1_15_2/historico_preservado.png) |
| Apresentação | [Janela](capturas/relevancia_gis_1_15_2/janela_independente.png), [painel estreito](capturas/relevancia_gis_1_15_2/painel_estreito.png) |
| Legenda / contexto WaterGEMS | [Símbolos por relevância](capturas/relevancia_gis_1_15_2/legenda_watergems.png) |
| Contexto de equipamentos | [Consulta opcional](capturas/relevancia_gis_1_15_2/contexto_equipamentos.png) |
| Nova sessão | [Decisão recuperada](capturas/relevancia_gis_1_15_2/reabertura_decisao.png) |

A comparação com a [1.15.1](INVESTIGACAO_GIS_1_15_1.md) evidencia a nova fila, a coluna de relevância junto ao ID, as explicações e a legenda. Tabelas estreitas usam rolagem/reticências com tooltip, sem ocultar os dados persistidos. Não houve teste físico de dois monitores.

## Desempenho comparativo

Benchmark de metadados em PyQGIS 3.44.15 / Python 3.12.15 / Windows 11, processador AMD64 Family 26 Model 96. A referência 1.15.1 foi lida do ZIP preservado, sobre os mesmos dados sintéticos. Dez repetições de construção e cem de filtragem. Houve outras verificações em execução no computador; estes valores não são garantia universal nem medição de rede hidráulica real.

Os cenários replicam registros sintéticos de eventos/locais; o maior não representa 20 mil novas geometrias GIS independentes. Não foi medida memória nem inicialização completa do QGIS neste benchmark.

| Cenário | Construção 1.15.1 — mediana / p95 / pior (ms) | Construção 1.15.2 — mediana / p95 / pior (ms) |
|---|---|---|
| Vazio | 0,0026 / 0,0046 / 0,0077 | 0,0065 / 0,0093 / 0,0184 |
| 745 locais / 1.112 eventos | 3,424 / 5,226 / 40,285 | 12,720 / 13,454 / 13,950 |
| 5.000 locais / 20.000 eventos | 135,572 / 199,192 / 203,938 | 379,502 / 518,823 / 535,364 |

| Filtro aquecido | 1.15.1 — mediana / p95 / pior (ms) | 1.15.2 — mediana / p95 / pior (ms) |
|---|---|---|
| Todos — 1.112 eventos | 0,047 / 0,056 / 0,064 | 0,595 / 0,797 / 0,951 |
| Classe — 1.112 eventos | 0,078 / 0,116 / 0,154 | 0,768 / 1,500 / 1,930 |
| Todos — 20.000 eventos | 0,321 / 0,476 / 1,087 | 8,592 / 13,907 / 14,150 |
| Classe — 20.000 eventos | 0,546 / 0,868 / 1,234 | 18,195 / 24,297 / 37,496 |

A fila por relevância, nova na 1.15.2, mediu 0,593 / 0,744 / 0,930 ms para 1.112 eventos e 18,749 / 32,505 / 37,134 ms para 20 mil. A classificação tem custo adicional real; não é apresentada como aceleração sobre uma versão que não a calculava.

A construção do índice ocorre no worker de criação/reabertura, validado por teste de thread. Selecionar um local usa o índice pronto. A consulta de equipamentos usa snapshots e índice espacial sob demanda; seu custo de leitura não está incluído nesses números. Não há auditoria geométrica nova a cada filtro ou seleção.

## Limitações e próximo passo

Não há detector novo de sobreposição entre tubos nem verificação de inserção topológica de equipamentos. A categoria Inconsistência identificada cobre a verificação referencial descrita, não validação hidráulica. A consulta de equipamentos reflete fontes atuais, sem inventar associações históricas. Reabrir uma base compartilhada mantém subset por execução; a gravação de QGZ com múltiplas execuções exige validação adicional de desktop, além da regressão de isolamento já executada.

Os testes desta entrega usam dados sintéticos, inclusive as bases anteriores e WaterGEMS associado. Não se afirma uma validação operacional de Franco da Rocha nem do WaterGEMS desktop. Ainda cabe aceitação do usuário sobre seu piloto, sem publicar esses dados.

Elementos e conexões complementares foram **planejados**, não implementados. A próxima etapa deve preservar UUIDs/revisões, separar existente informado/a confirmar/proposto/hipotético e exigir participação explícita na hipótese, sem alterar as fontes ou inserir conexões automaticamente.
