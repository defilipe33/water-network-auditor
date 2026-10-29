# Ilhas sem caminho até origem — 1.10.0

A categoria **REDE SEM CAMINHO ATÉ ORIGEM DE ABASTECIMENTO** identifica conjuntos investigáveis, inclusive redes extensas. Ausência de caminho cadastrado não comprova desabastecimento, vazão, pressão ou necessidade de conectar elementos.

## Como usar

1. Abra a investigação integrada e escolha **Ilhas sem origem**, no painel ou no módulo de corredores.
2. Escolha Reservoirs elegíveis, Reservoirs e Tanks, origens selecionadas ou personalizadas. Tanks exigem assumir explicitamente sua utilização como hipótese. Uma Junction selecionada é ponto inicial de análise, não fonte hidráulica comprovada.
3. Confira origens encontradas/utilizadas. Se não houver nenhuma, o resultado será **SEM ORIGENS / inconclusivo**, sem classificar toda a rede como defeituosa.
4. Configure, se necessário, restrições de equipamentos e prioridade. Calcule sobre o grafo completo da versão, não apenas sobre a seleção cartográfica.
5. Selecione uma ilha, destaque seus membros e use **Aproximar** somente quando desejar alterar o enquadramento. Grupos sem tubulações são preservados e podem ser mostrados pela opção correspondente.
6. Salve e use **Analisar no painel** para registrar resultado, observação, prioridade de trabalho ou RESOLVIDO. Nenhum responsável ou documento é obrigatório. As decisões utilizam o histórico existente da investigação.
7. Exporte inventário, membros e Queries por tipo ou gere o relatório da investigação. O conjunto não é um percurso ordenado. O comando de elementos alcançáveis permite exportar o complemento investigativo da análise.

## Duas análises diferentes

**ESTRUTURAL:** busca multiorigem pela conectividade fraca do grafo de referência, incluindo os elementos inativos previstos no contrato estrutural. Responde se existe ligação cadastrada independentemente de sua operação.

**RESTRITA:** busca dirigida a partir das origens no grafo da hipótese **TODAS_VALVULAS_ABERTAS**, respeitando Active Topology, direção obrigatória, limitações de bombas/dispositivos e restrições existentes. EVITAR é preferência de rota e não elimina alcançabilidade; BLOQUEAR remove a travessia somente na cópia de trabalho. A origem bloqueada exige escolha explícita. Se nenhuma origem permanecer disponível, essa análise será inconclusiva.

Os conjuntos restritos são adicionais aos estruturais: as mesmas tubulações não são contadas duas vezes. Elementos fora da perspectiva, referências incompletas, tubos na fronteira de um dispositivo removido e dispositivos apenas parcialmente alcançados têm inventários distintos. Conectividade fraca não substitui alcance dirigido.

**ESTADOS_DO_CENARIO continua indisponível.** Os resultados não demonstram a disponibilidade operacional efetiva de Tanks, bombas ou controles.

## Inventário e prioridade

Cada ilha tem UUID derivado da assinatura da execução/configuração e de sua composição, portas topológicas, membros, componentes, tubulações, Junctions, dispositivos, comprimento quando validado e extensão espacial quando disponível. Regiões e ocorrências existentes são relacionadas apenas por vínculos persistidos comprovados; não se inferem setores pelo texto dos diagnósticos.

O padrão de prioridade Alta utiliza participação relativa de 1% das tubulações do universo analisado. É configurável, assim como limites absolutos opcionais de quantidade e comprimento. A justificativa é exibida e a prioridade manual permanece independente. Não há limite universal obrigatório de tubos nem classificação hidráulica automática.

Customer Meters, demanda e população permanecem **indeterminados** quando as relações/unidades não estiverem validadas. Regiões sem relações persistidas não recebem pertencimento inventado.

## Candidatos e mapa

A busca espacial exige referência métrica validada. Examina extremidades de todas as partes das tubulações da ilha junto a redes efetivamente alcançadas, com raio explícito e índice espacial. Bloqueios, inatividade e referências incompletas também podem ser investigados sem comparação espacial.

A lista possui limite explícito de 200 candidatos, informa quantos foram omitidos e permite refinar o raio. Proximidade é hipótese investigativa, nunca conexão. Um candidato com posição comprovada pode originar local manual; candidatos sem posição não recebem coordenada inventada. Destaques temporários preservam os estilos das fontes; o zoom é explícito.

## Persistência e desempenho

A extensão reside no mesmo GPKG integrado: `IGD_ILHAS_SCHEMA`, `IGD_ILHAS_ANALISES`, `IGD_ILHAS`, `IGD_ILHAS_MEMBROS` e histórico de seleção `IGD_ILHAS_ATIVAS`. UUIDs de investigação e versão topológica são referências obrigatórias. A primeira extensão cria backup verificado; as gravações são transacionais e o histórico imutável. Bases antigas podem ser consultadas sem migração na leitura.

A assinatura inclui algoritmo, elementos, grafos, contexto e relações. Resultados compatíveis são reutilizados antes de executar BFS. Cálculo, persistência, candidatos e comparação utilizam o acompanhamento de atividades e workers existentes; cancelamento é cooperativo e não publica resultados parciais. Não se realiza uma busca completa para cada tubo.

## Comparação e relatórios

Selecione uma investigação anterior com análise de ilhas salva. A comparação utiliza UID/tipo dos membros, composição, incidências topológicas, disponibilidade, cenário, alternativas, origens e regras. Distingue permanência, composição alterada, não observada, nova ilha, correspondência incerta e reavaliação necessária. Não observada não significa corrigida. Nenhuma conclusão ou RESOLVIDO é transferida automaticamente.

A comparação utiliza `IGD_COMPARACOES`, já existente. A tabela mostra até 200 registros com indicação explícita; JSON conserva a comparação completa. Mudanças de alcance são evidências para revisão, não aprovação hidráulica.

O PDF e o XLSX incluem a seção **REDES SEM CAMINHO ATÉ ORIGEM**, origens, regras, inventário e situação de investigação. Resultado técnico e acompanhamento permanecem separados. Mapas offline reutilizam o renderizador e os controles de basemap existentes. Queries exportam exatamente os membros identificados; criação de Selection Set nativo exige conferência no WaterGEMS desktop e não é declarada automática.

## Verificação de aceitação

- QGIS 3.44.15: instalar o ZIP em perfil de teste e abrir uma cópia da investigação.
- Calcular com Reservoirs; repetir com Tank explícito, Junction personalizada e nenhuma origem.
- Comparar estrutural/restrita, bloquear equipamento e confirmar diferenças e destinos alcançados.
- Ordenar por tamanho; consultar grupos sem tubos, regiões e referências incompletas.
- Selecionar, destacar, aproximar explicitamente e criar local manual a partir de candidato.
- Salvar observação/resultado sem responsável, marcar RESOLVIDO e verificar filtros.
- Exportar membros/Queries, conferir totais por tipo e relatório offline.
- Fechar realmente o QGIS; abrir em outra sessão; recuperar análise, cache, histórico e comparação.
- Cancelar um processamento e confirmar integridade das versões anteriores.

A entrega inclui regressões sintéticas e ensaios pela API Qt em processos reais do QGIS com o pacote instalado. **Aceitação visual humana e conferência no WaterGEMS desktop permanecem pendentes.** Nenhum modelo hidráulico ou cadastro original é modificado.
