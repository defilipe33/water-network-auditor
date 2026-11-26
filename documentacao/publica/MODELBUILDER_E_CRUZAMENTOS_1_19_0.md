# Preparação para ModelBuilder e revisão de cruzamentos

## Exportar modelo para WaterGEMS

Em **Investigar minha rede → Exportar modelo para WaterGEMS**, abra uma execução de conectividade e selecione **Exportar modelo para WaterGEMS** no grupo de exportações. O assistente usa a revisão do Modelo GIS associada à execução. A regra de atividade escolhida na prévia permanece registrada. O cadastro completo inclui tubulações isoladas e partes fora da hipótese. Uma fonte ausente, filtrada no provedor ou com geometrias descartadas fica no relatório de cobertura.

1. Para recortar o resultado, selecione hipótese, origem alcançável, corredores, blocos, áreas ou conjuntos salvos. A seleção por área é espacial.
2. Configure as propriedades hidráulicas que possuem atributo e unidade conhecidos. O comprimento geométrico é em metros. Comprimento hidráulico conhecido e coeficiente Hazen-Williams têm campos próprios. Um comprimento informado para o Pipe físico exige revisão antes de ser atribuído a um trecho dividido.
3. Escolha a versão de destino, o formato e os conjuntos. Salve o perfil para reutilização. Prefira Shapefile quando for testar a importação no ModelBuilder standalone. GeoPackage e CSV ficam disponíveis para conferência e interoperabilidade.
4. Consulte `WNA_TOPOLOGIA_ESPERADA.csv`, `WNA_PENDENCIAS_MODELBUILDER.csv` e `MODELBUILDER.json`. Os nós das pontas estão em `MB_INICIO` e `MB_FIM`, por Label previsto. Divergências de coordenadas e nós distintos coincidentes exigem conferência. Conexões em T confirmadas usam a Junction comum e os segmentos já resolvidos. Cruzes sem ligação continuam independentes.

O perfil e as exportações são revisões do GeoPackage de complementos. Pacotes internos usam caminhos relativos ao manifesto `.wna`. Pacotes externos podem ser relocalizados pela conferência. As revisões anteriores do cadastro, da hipótese e dos conjuntos continuam disponíveis.

### Equipamentos

Reservoirs precisam de um vínculo declarado com um único nó e de carga conhecida. Tanks cilíndricos precisam de vínculo, elevação da base, níveis mínimo, inicial e máximo relativos à base e diâmetro. A saída específica substitui a Junction de apoio no mesmo nó quando todos os requisitos são atendidos. O identificador desse nó continua sendo a referência dos Pipes.

Quando dois equipamentos disputam o nó, faltam atributos ou a geometria diverge, consulte as pendências. Bombas, boosters, válvulas e outras singularidades estão no inventário. A inserção desses elementos requer um contrato de portas, direção e propriedades hidráulicas que seja válido no modelo de destino.

## Importação, mapeamento e conferência

Use uma cópia do modelo ou crie um modelo de ensaio. No vínculo de Shapefile, inclua conjuntamente todos os tipos exportados. Escolha as unidades do pacote. Configure `WNA_LABEL` como Label/chave de criação e importe `WNA_UID` como UDE de texto. Mapeie `MB_INICIO` e `MB_FIM` para Start Node e Stop Node. Mantenha desligadas as opções de conexão espacial, criação de nós ausentes e remoção de elementos. A conexão espacial por tolerância pode unir Pipes que compartilham coordenadas sem compartilhar um nó. [Importação com ModelBuilder](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0057220) · [Mapeamento de Start/Stop Node](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0016117).

O `ID_GIS` original continua em `WNA_ID_GIS`, inclusive zero e valores repetidos. Se a instalação exigir usar o mecanismo GIS-ID como vínculo, escolha uma chave técnica cuja unicidade tenha sido conferida na fonte e no destino. Preserve a procedência cadastral em outro campo. [Sincronização de GIS com ModelBuilder](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0057080) · [User Data Extensions](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015506).

Depois da operação, exporte as FlexTables e organize uma linha por elemento no leiaute `MODELO_CONFERENCIA_WATERGEMS.csv`. Os campos `no_a` e `no_b` da **evidência** recebem o identificador efetivo dos nós no WaterGEMS, enquanto os mesmos campos da tabela **esperada** guardam os UIDs WNA. Informe as coordenadas no CRS métrico do pacote e mantenha os valores nulos vazios. Informe o cenário e a alternativa para conferir atividade. Abra **Exportações ModelBuilder e conferência** e selecione o CSV. O relatório registra ausências, duplicidades, coordenadas, conectividade e diferenças de atributos. O GeoPackage `correspondencias.gpkg` contém `WNA_ELEMENTO_WATERGEMS` com os vínculos de identidade e topologia que passaram pela conferência.

Na atualização, use um pacote anterior do mesmo projeto. O plano indica elementos preservados, novos, alterações e substituições manuais por divisões comprovadas na identidade da parte e no intervalo. Compare a FlexTable completa e confira o vínculo de cada elemento antes de executar o ModelBuilder. Uma chave ausente ou alterada exige conferência antes de adicionar objetos. Em caso de divisão, trate o Pipe anterior e os segmentos em uma cópia. A Bentley oferece Batch Pipe Split para certos casos de nós sobrepostos, mas esse procedimento requer controle das interligações. [Batch Pipe Split](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015764).

Use as minutas e a tabela `WNA_ELEMENTO_CONJUNTO` para conferir os membros de cada conjunto por tipo. A atividade pretendida tem CSV e minutas próprias por estado. Aplique a atividade explícita na alternativa do cenário desejado. Preserve o cenário original e confira os resultados na FlexTable. [Criação de Selection Sets](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015896) · [Active Topology](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0014397).

### Compatibilidade e nível de evidência

| Recurso | WaterGEMS 2020, CONNECT | WaterGEMS 2026, série 26.00 | Preparação WNA |
|---|---|---|---|
| Shapefile, atributos e conexão por campos | Procedimento oficial CONNECT | Procedimento oficial OpenFlows | Exportado e reaberto no QGIS |
| CSV tabular | Conferir provedor da instalação e mapeamento | Conferir provedor da instalação e mapeamento | Tabelas, coordenadas e WKT. Preservação de bends na importação por CSV pendente |
| GeoPackage como fonte direta standalone | Sem comprovação | Sem comprovação | Produto GIS |
| Snapshots e conexão `.mbc` | Documentados desde CONNECT Update 1 | Recursos documentados, conferir no ambiente | Perfil WNA e ficha. Exporte o `.mbc` pelo próprio ModelBuilder quando disponível |
| UDE textual e Selection Sets | Recursos documentados | Recursos documentados | Minutas por tipo e lote, a validar no modelo |
| Active Topology | Alternativa e seleção manual | Alternativa, seleção manual e modo por consulta introduzido em 2024 | Atividade pretendida e procedimento de conferência |

O guia usa CRS projetado e métrico para manter um fluxo comum entre as versões. A Bentley documenta suporte à reprojeção direta de fontes geográficas a partir da série 26.00. [Coordenadas geográficas no ModelBuilder](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0014824) · [Snapshots do ModelBuilder](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0016034).

## Prioridade dos cruzamentos

Em **Analisar conectividade**, escolha **Cruzamento ambíguo**. O filtro inicial mostra cruzamentos prioritários. Na fila sequencial, mantenha **Somente pendentes ou indeterminadas** para trabalhar primeiro nos cruzamentos prioritários ainda sem veredito. Use os filtros para consultar os intermediários, os de baixa prioridade, os próximos a pontas, os isolados ou os já revisados.

O limiar inicial acompanha a tolerância da execução. A distância até a ponta é medida ao longo do Pipe. A prioridade é alta para proximidade de ponta, para uma ocorrência entre componentes distintos com um sem origem alcançável ou para uma tubulação isolada que cruza outro componente. É intermediária para componentes distintos em cruzamentos internos e para referências incompletas. É baixa para cruzamentos internos do mesmo componente. Quando há uma única candidata em T com as mesmas partes e posições compatíveis em ambos os Pipes, a fila prioritária direciona a revisão à conexão em T. As duas referências permanecem disponíveis na auditoria.

A prioridade orienta a investigação. A geometria do cruzamento permanece separada até a aplicação de uma decisão explícita. A baixa prioridade conserva o estado **Não revisado**. O veredito **Sem conexão** mantém seu acompanhamento e seu histórico.
