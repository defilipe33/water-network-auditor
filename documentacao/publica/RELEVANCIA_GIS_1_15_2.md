# Investigação GIS — relevância das ocorrências (1.15.2)

O fato geométrico, a relevância e a situação da investigação são informações diferentes. Uma travessia pode ser **Informativa** e continuar **Pendente**. Marcar **Verificado** registra a avaliação do usuário, sem comprovar correção ou operação hidráulica.

## O que o motor geométrico realmente identifica

| Classificação original | Significado / representação |
|---|---|
| TRAVESSIA | Amostras antes e depois do encontro indicam mudança de pertencimento ao polígono. O ponto representa esse encontro. |
| TANGENCIA | Contato com a fronteira sem mudança de pertencimento nas amostras. |
| EXTREMIDADE | Falta uma amostra antes ou depois porque o evento está na extremidade da linha. Não é um detector de componentes sem alimentação. |
| COINCIDENCIA | Intervalo da linha coincidente com a **fronteira poligonal**, não uma classificação de sobreposição entre tubos. O ponto cartográfico fica no meio do intervalo; a geometria técnica continua sendo o trecho. |
| CONTINUIDADE_POTENCIAL | Par de extremidades próximas, em lados opostos da fronteira, segundo os critérios existentes. O ponto é o meio das extremidades, não uma conexão criada. |
| AMBIGUA | A verificação geométrica não resolveu o pertencimento de maneira inequívoca. |

Sobreposição entre tubulações e cruzamento entre tubos não ganham um novo detector nesta atualização. Classes desconhecidas em resultados recebidos permanecem **Indeterminadas**, sem conversão arbitrária para uma classe conhecida. A apresentação mantém IDs, classificação, vínculos e geometria técnica originais.

## Regras implementadas

Regra reproduzível: `gis-relevancia-1`.

| Condição observada no resultado | Relevância |
|---|---|
| Vínculo explícito para uma tubulação ausente do inventário do resultado | Inconsistência identificada **de referência do resultado**, não falha hidráulica |
| Falta classificação ou vínculo de tubulação | Indeterminada |
| Continuidade potencial | Revisar |
| Classe ambígua ou ambiguidade técnica/de identificação registrada | Revisar |
| Travessia, tangência, extremidade ou coincidência com fronteira, sem outro indício | Informativa |
| Classe sem regra conhecida | Indeterminada |

A prioridade das regras segue a ordem da tabela. Cada evento recebe motivo, critério, versão da regra e assinatura dos dados usados. O acompanhamento e as observações não participam desse cálculo. A categoria de inconsistência não verifica ainda inserção topológica obrigatória de válvulas ou bombas: isso depende do grafo GIS futuro.

Estar próximo de booster, reservatório ou válvula não muda a relevância. Setores e zonas são referências GIS e não barreiras hidráulicas presumidas. Uma coincidência com a fronteira não é rotulada automaticamente como inconsistência.

## Como usar

1. Abra um trabalho GIS existente ou execute a análise pelo Modelo GIS, sem exigir WaterGEMS.
2. A fila inicial **Precisam de revisão** inclui locais com eventos Revisar ou Inconsistência identificada. Um local misto continua mostrando todos os seus eventos relacionados, cada um com sua própria relevância.
3. Escolha **Todas as ocorrências**, **Informativa** ou **Indeterminada** para consultar os demais registros. Uma fila vazia não significa que os eventos foram apagados. As contagens são por evento único, não pela soma de membros dos agrupamentos.
4. Combine relevância, classificação geométrica, modo de análise, situação, pesquisa por local/tubulação e setor/zona (nome, ID ou camada persistidos). As condições de classe/relevância/região precisam corresponder ao mesmo evento do local.
5. Em DETALHES DO LOCAL, escolha uma ocorrência para ler o significado e o motivo da relevância. Situação e observação permanecem em ANÁLISE E DECISÃO, com histórico individual e do agrupamento preservados.
6. Selecione um único ponto na camada própria **Ocorrências geométricas** usando a seleção do QGIS. O painel abre seu UUID e agrupamento. Essa ação explícita limpa filtros que poderiam ocultá-lo, informa isso e não altera o zoom. Rascunhos continuam protegidos por Salvar/Descartar/Cancelar. Múltiplos pontos selecionados não escolhem arbitrariamente um evento.
7. **Destacar** mantém tubos em azul, o ponto do agrupamento em violeta e ocorrências por relevância. **Aproximar local** continua explícito; não há zoom ao apenas selecionar um caso.

### Equipamentos sob demanda

Em **Equipamentos próximos e associações declaradas**, ajuste a distância em metros e use **Consultar / atualizar equipamentos**. O worker consulta as fontes atuais e monta um índice espacial reutilizável; não há leitura de todas as camadas a cada seleção. Tipos incluem válvulas, bombas, boosters, reservatórios, tanques, hidrantes e dispositivos cadastrados.

Os resultados distinguem **Proximidade geométrica apenas** de **Associação declarada**. Uma associação manual existente a Reservoir/Tank é conferida por identidade, tipagem do ID, unicidade, filtro e assinatura da feição de tubulação. Não se exige coincidência espacial entre instalação e tubo. Apenas associações recuperadas com segurança acrescentam equipamentos ao destaque do local. A geometria de equipamento ausente não é inventada.

O filtro por equipamento é habilitado após essa consulta e procura ID, nome, categoria, fonte ou natureza da relação. A consulta descreve **fontes atuais**, não reconstrói silenciosamente o estado histórico dos equipamentos. Mudança de dados, fonte, esquema, CRS, filtro, projeto ou remoção de camada invalida o contexto; ajuste de distância e edição do Modelo GIS também exigem atualizar. Alterações externas a arquivos sem sinal do provedor requerem uma atualização explícita. IDs repetidos não são fundidos como associação confirmada.

### Legenda e preservação de estilos

Na camada própria: círculo azul-cinza = Informativa; triângulo âmbar = Revisar; losango vermelho = Inconsistência identificada; quadrado roxo = Indeterminada. A legenda usa forma e nome, além da cor. No destaque temporário, a revisão usa cruz âmbar (ícone disponível no QgsRubberBand 3.44), mantendo o significado da cor.

O campo virtual `WNA_RELEVANCIA` e o renderer pertencem à camada gerenciada no projeto QGIS. Não há escrita nos dados GIS originais nem no GeoPackage carregado. A simbologia personalizada do usuário é preservada ao reabrir; o estilo padrão só é reaplicado quando ainda é o estilo da ferramenta. O ponto representativo do grupo continua diferente da geometria técnica do evento.

## Persistência e exportação

Não há migração das bases nem regravação de decisões para classificar relevância. Trabalhos antigos são interpretados em memória com a regra indicada na tela. Novos trabalhos registram a versão da regra em sua configuração.

**Shapefile e tabelas** preserva todas as saídas existentes e acrescenta `RELEVANCIA_EVENTOS.csv`: execução, UUID, classe geométrica, relevância, motivo, critério, regra e assinatura. O vínculo ao SHP é feito pelo UUID técnico existente, evitando truncar motivos em campos DBF.

**GeoPackage completo** cria uma cópia verificada e acrescenta `WNA_RELEVANCIA_EVENTOS` somente nessa cópia. A chave é execução + evento. O arquivo anterior, as revisões e os resultados originais permanecem intactos. Filtros da fila não removem eventos das exportações. Destinos existentes não são sobrescritos.

## Arquivos e arquitetura

- `relevancia_gis.py`: regras puras sobre eventos/vínculos, sem acesso a fontes GIS.
- `investigacao_gis.py`: índice, contagens e filtros; decodificação de geometrias continua sob demanda.
- `painel_investigacao_gis.py` e `analise_gis_ui.py`: fila, explicações, contexto opcional e seleção mapa → evento.
- `mapa_relevancia_gis.py` e `mapa_fontes.py`: estilo de resultados e destaques temporários.
- `contexto_equipamentos_gis.py`: snapshots, índice espacial e validação conservadora de associações.
- `analise_modelo_gis.py` e `exportacao_investigacao_gis.py`: proveniência e exportação adicional.

Os motores geométricos, o agrupador, o leitor WaterGEMS e os contratos de revisão permanecem reutilizados. Não há novas conexões, elementos complementares ou escrita no WaterGEMS.

## Aceitação manual

Abra uma base da 1.15.1 e confira as contagens e a identificação da regra. Examine uma travessia simples em Todas as ocorrências e confirme Informativa/Pendente. Examine uma continuidade candidata na fila de revisão. Selecione o ponto no mapa e confira ID, tubulações e polígonos no painel. Registre Verificado sem observação e reabra o histórico. Consulte equipamentos e compare proximidade com associação declarada, incluindo reservatório afastado. Mude uma fonte e confira a invalidação. Exporte SHP/tabelas e GPKG, compare o total de eventos com Todas as ocorrências. Reabra o trabalho, alterne painel/janela e temas e confirme decisões e símbolos.

## Limitações

Relevância interpreta os fatos disponíveis; não valida abastecimento, sentido de vazão, inserção de dispositivos ou conectividade GIS. Contagens podem incluir zero inconsistências. A consulta opcional de equipamentos pode custar proporcionalmente ao tamanho de suas fontes, com cancelamento cooperativo. A camada de eventos usa expressão virtual para o estilo; redes muito maiores que as amostras ensaiadas exigem medir também seu custo de renderização.

Consulte o [roadmap de topologia e elementos complementares](ROADMAP_GIS_ELEMENTOS_COMPLEMENTARES.md). Os resultados e limites dos ensaios acompanham as notas da pré-release.
