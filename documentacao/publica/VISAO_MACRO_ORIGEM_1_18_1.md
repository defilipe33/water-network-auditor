# Visão macro do abastecimento por origem

## Uso no QGIS

1. Abra um projeto `.wna` e uma execução salva em **Investigar minha rede → Redes estruturantes**.
2. Em **Visão macro do abastecimento por origem**, selecione uma origem, um subconjunto, todas as habilitadas ou duas para comparar. A execução topológica determina quais origens estão habilitadas e quais portas estão vinculadas.
3. Clique em **Calcular visão integral**. O resumo registra Pipes alcançáveis, Pipes fora do alcance, cobertura dos blocos, extensão dos corredores e extensão da rede restante.
4. Abra **Mapa, árvore e exportação**. Escolha a apresentação e clique em **Mostrar no QGIS**. O padrão combina corredores azuis com grupos de linhas em cores suaves. A opção **Completa com rede de contexto** usa linhas cinza para a rede fora da seleção.
5. Use **Geral**, **Por bloco** e **Detalhada** para consultar as tabelas. Há também listas específicas de áreas GIS, segmentos, nós e conexões declaradas. Na árvore e na tabela, clique para ler detalhes, dê duplo clique para aproximar e use o menu de contexto para consultas, revisões e exportação.
6. Escolha uma área ou um bloco e use **Mostrar caminho desde o reservatório**. O destaque reúne os percursos de referência até os nós dos segmentos selecionados. Os trajetos podem sair da área selecionada. A ação **Restaurar visibilidade das camadas** volta à apresentação anterior do QGIS.

O menu de um bloco permite renomeá-lo, associar uma área, reunir blocos contíguos ou selecionar segmentos para dividi-lo em dois grupos conectados. Renomear um corredor preserva sua identidade. As mudanças geram revisões e o menu **Ações da visão macro** permite reabrir a proposta automática. Em **Meus trabalhos**, o projeto recupera a fotografia, os resultados, a apresentação e o destaque salvos. Trabalhos das versões anteriores continuam acessíveis nas análises estruturais detalhadas.

## Critério técnico

Na 1.18.0, os corredores de referência eram derivados das rotas até destinos selecionados, incluindo a amostra automática de destinos representativos. Os blocos técnicos separavam a rede em malhas e sequências de pontes. A sobreposição das representações e dos diagnósticos dificultava ler o mapa em escala municipal.

Na 1.18.1, uma busca por componentes determina a cobertura integral da execução, inclusive malhas, ramificações curtas e trechos ausentes da árvore de referência. Sobre a mesma fotografia, Dijkstra multiorigem calcula a menor distância acumulada em metros. Os desempates usam a identidade dos nós e segmentos. Entre as ramificações de cada raiz, o tronco segue o filho com maior extensão acumulada na subárvore. O comprimento mínimo dos demais ramais controla seu destaque. O trecho continua contabilizado quando fica abaixo desse limiar.

A decomposição em blocos biconexos preserva pontes e articulações nos detalhes. Para criar blocos macro, os ramos menores permanecem junto ao grupo a que se ligam e ramificações maiores podem iniciar outro grupo. A opção **Orientar os blocos pelas áreas GIS** considera a área de maior interseção linear em cada bloco detalhado e pode iniciar outro grupo em mudanças de área, respeitando o limiar. Uma malha biconexa pode permanecer inteira como um bloco. Cada segmento alcançável pertence a exatamente um bloco macro. Um Pipe físico pode participar de blocos diferentes após divisões virtuais. A contagem total usa a identidade física e atribui cada Pipe a um bloco principal para permitir somas sem duplicação.

A comparação por origem usa os componentes do grafo completo para distinguir alcance compartilhado, exclusivo e fora do alcance. As referências individuais usam árvores próprias por origem. A vista **Influência por distância em rede** mostra vencedores, transições e empates entre origens. A verificação de alternativa exclui todos os Pipes físicos do percurso escolhido até um destino representativo. A presença de um trecho fora da árvore indica uma ligação que pode ser investigada. A classificação da alternativa independente depende do teste explícito.

Áreas GIS funcionam como referência espacial. A associação manual registra o vínculo declarado separadamente. Os comprimentos das interseções por área podem se sobrepor. A soma entre áreas pode exceder a extensão da rede. Sem origem habilitada, a análise fornece pontes, articulações e blocos detalhados e mantém o alcance indeterminado. O resultado representa conectividade sob a hipótese escolhida. Pressão, vazão, sentido do escoamento e capacidade de abastecimento permanecem fora da análise.

## Exportação

Use o menu contextual ou **Ações da visão macro** para exportar um corredor, um bloco, vários blocos, uma área, seus percursos de referência, os corredores apresentados ou a rede alcançável. GeoPackage e Shapefile incluem Pipes segmentados e Junctions. A opção CSV inclui WKT, CRS no manifesto e as relações de origem. Os Shapefiles acompanham um dicionário de campos e tabelas com identificadores completos.

Quando a seleção depende de trechos externos à área ou ao bloco, marque **Incluir segmentos de referência externos à seleção** para adicioná-los ao pacote. O campo `continuidade` identifica esses segmentos. O arquivo `validacao.json` registra o escopo, os trechos de referência externos, a origem, a hipótese, a execução, as divisões e as pendências geométricas. Os vínculos de conexão indicam se suas partes estão presentes. O pacote serve para conferência cartográfica antes da montagem do modelo.

## Ensaio de escala

No Windows com PyQGIS 3.44.15 e Ryzen AI 7 350, foram feitas três medições do cálculo sobre cada fotografia sintética com 32.400 nós, seguidas de uma execução separada com `tracemalloc`. Medições de CPU e memória se referem ao motor Python. Preparação das fontes, renderização e gravação dos trabalhos têm custos próprios.

| Rede | Segmentos | Blocos 1.18.0, mediana | Visão 1.18.1, mediana | Comparação de duas origens, mediana | Pico Python na visão integral |
| --- | ---: | ---: | ---: | ---: | ---: |
| Malhada | 64.440 | 0,80 s | 1,44 s | 1,81 s | 105 MiB |
| Ramificada | 32.399 | 0,80 s | 1,42 s | 1,73 s | 104 MiB |

Os dois casos contabilizaram todos os segmentos. O ensaio de referência da 1.18.0 mede somente o agrupamento de blocos sobre a fotografia, sem o cálculo anterior de rotas. A comparação tem escopos diferentes.
