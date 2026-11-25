# Etapa 2 — Topologia GIS independente

A análise de conectividade usa as tubulações cadastradas no Modelo GIS. O resultado descreve a conectividade estrutural da execução e o acesso às origens selecionadas na hipótese.

## Executar no QGIS

1. Instale o ZIP pelo gerenciador de complementos do QGIS. No menu `⋯` do Auditor, escolha **Novo projeto (.wna)** ou **Abrir projeto (.wna)**. Use **Gerar arquivo .wna do projeto atual** para migrar um projeto existente, mantendo seu UUID, revisões e trabalhos.
2. Cadastre as fontes de tubulações em **Preparar minha rede**. Escolha o identificador, o filtro e os atributos disponíveis. Para investigar setores, só mapeie **Setor operacional declarado** quando o campo representar essa informação.
3. Abra **Investigar minha rede → Analisar conectividade**. Confira o CRS métrico, o escopo e a tolerância. A configuração inicial marca todas as redes cadastradas e sugere 0,20 m. Se houver diâmetro, selecione a unidade por fonte. Diâmetros sem unidade confirmada aparecem como indisponíveis.
4. Execute a análise mesmo que o projeto consista somente de tubulações. Os componentes aparecem antes de qualquer configuração de origens. O componente principal é o mais extenso no escopo analisado.
5. Use **Definir fontes de água e conexões** para escolher um reservatório, tanque ou ponto de entrada cadastrado. Para uma entrada complementar, clique em **Adicionar origem no mapa** e posicione-a. Associe uma ou várias portas por ID, camada, parte e posição ao longo da linha. O local do equipamento e as portas associadas podem estar afastados.
6. Marque separadamente os registros que participarão da execução. A lista inclui fontes cadastradas, existentes informadas, a confirmar, propostas e hipotéticas. Salvar uma hipótese registra sua seleção. Cada execução registra as revisões exatas que utilizou. Novas revisões não alteram trabalhos publicados.
7. Filtre por categoria e ordene por prioridade, comprimento ou diâmetro. Use **Destacar seleção** e **Aproximar seleção** para examinar o resultado. O filtro por zona apenas controla o que aparece na lista, após a construção do grafo.
8. Para revisar um T, cruzamento ou par de pontas, escolha o resultado e use **Revisar conexão selecionada**. Registre a interpretação, marque a revisão e execute outra hipótese. Use **Histórico** para consultar as versões e **Comparar com uma execução anterior** para ver mudanças de componentes e de acesso às origens.
9. Reabra um resultado por **Meus trabalhos → Conectividade GIS**. Para levar as geometrias ao QGIS ou a outro projeto, exporte GeoPackage ou Shapefile e tabelas.

## Contratos de interpretação

- **Junctions** seguem a estratégia do Modelo GIS. A opção cadastrada exige uma Junction única. A opção inferida usa extremos e a combinada tenta primeiro os nós cadastrados. Grupos de pontas com evidência ambígua permanecem separados. A união de pontas próximas requer configuração explícita e distância dentro da tolerância para todos os pares do grupo.
- **Possível T** exige uma ponta próxima de uma projeção no interior da receptora. O registro conserva as portas, projeção, distância, receptores concorrentes e nós cadastrais ou pontas próximas. Confirmar uma porta interna divide virtualmente o trecho receptor. O comprimento original é contabilizado uma vez.
- **Cruzamentos entre interiores** ficam separados até confirmação. **Sobreposições** representam trechos coincidentes para investigação. As relações declaradas conservam a natureza e a revisão utilizadas.
- **Origens** participam quando selecionadas e com portas válidas. Uma origem declarada ligada a duas redes pode habilitar acesso às duas. A relação a uma mesma instalação, por si só, não insere uma conexão de trânsito entre os componentes.
- **Rede principal sem ligação conhecida** usa o limite configurado de diâmetro ou a classificação cadastral de adução, junto com isolamento, ausência de caminho até origem ou candidatas não resolvidas. O limite inicial é 200 mm.
- **Possível mistura de setores** depende de uma conexão declarada selecionada e de setores operacionais distintos explicitamente mapeados. Relações espaciais de interseção são exibidas à parte.
- **Prioridade** ordena pelos componentes sem acesso, comprimento, diâmetro máximo, quantidade de candidatas e quantidade de trechos, nessa ordem. As ordenações diretas deixam o usuário escolher outro critério.

## Arquivos e histórico

O `.wna` preserva a identidade do projeto, referências ao Modelo GIS e suas revisões e referências às bases de trabalho. Caminhos de bases sob a pasta do projeto são relativos. Referências externas permanecem no endereço original. Fontes GIS locais reconhecidas podem ser recuperadas em modo de leitura. Fontes de memória, serviços e arquivos movidos precisam ser abertos ou relocalizados no QGIS.

Um GeoPackage próprio guarda as revisões de origens, conexões, hipóteses e decisões. Cada análise salva em outro GeoPackage os parâmetros, participantes, diagnósticos, grafo e geometrias de inspeção. Reabrir o trabalho usa a fotografia persistida. Mudanças no Modelo GIS, assinatura da camada ou revisão participante sinalizam a possível desatualização do resultado. O índice local e o catálogo continuam gerenciando as referências.

**Meus trabalhos → Localizar arquivo do trabalho** recupera uma referência ausente pela identidade. A área de fontes de água permite relocalizar o GeoPackage de complementos. Para relocalizar as entradas GIS, use a função correspondente do Modelo GIS. Mantenha os dados externos junto ao projeto ao transportar a pasta ou relocalize-os após a mudança.

## Desempenho e limites da entrega

O grafo usa índices espaciais para gerar candidatos e união por conjuntos para agrupar portas e componentes. A leitura de snapshots, construção e gravação ocorrem em worker. A navegação usa o resultado já construído. A exportação oferece campos curtos compatíveis com DBF e tabelas CSV que preservam identificadores.

Em QGIS 3.44.15 / Python 3.12.15 no Windows, uma malha sintética de **31.250 tubulações e 15.875 nós** levou **6,50 s** de mediana e **6,66 s** no pior caso de três repetições. A medição começa com as geometrias já carregadas. Leitura dos provedores, exportação e custo de redes com muitas sobreposições podem ter outro perfil.

A análise nesta etapa é estrutural. Os estados de abertura/fechamento, pressão, vazão e cotas ficam fora do cálculo. O acervo municipal real, fontes remotas e topologias com muitos segmentos paralelos continuam candidatos a ensaios de aceitação. O editor prioriza entradas, reservatórios, tanques e relações entre tubulações; edição hidráulica de outros equipamentos e exportação completa para ModelBuilder ficam no roadmap.

## Organização do código

| Área | Arquivos |
|---|---|
| Manifesto, índice e navegação | `manifesto_projeto.py`, `contexto_trabalho.py`, `ambiente.py`, `quadro_modelo.py`, `gerenciamento.py` |
| Modelo GIS e grafo | `modelo_gis.py`, `modelo_gis_ui.py`, `entradas_grafo_gis.py`, `grafo_gis.py`, `diagnosticos_grafo_gis.py`, `executar_grafo_gis.py` |
| Resultados, revisões e interface | `persistencia_grafo_gis.py`, `exportar_grafo_gis.py`, `topologia_gis_ui.py`, `complementos_gis_ui.py` |
| Ensaios | `test_grafo_gis.py`, `medir_grafo_gis.py` |
