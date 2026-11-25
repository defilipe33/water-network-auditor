# Water Network Auditor 1.18.0

## Salvar e retomar

Use **Salvar projeto** no cabeçalho do Quadro do Modelo. O menu **⋯** também oferece a ação. O complemento salva o cadastro confirmado, registra o estado consultado e preserva o rascunho da hipótese junto ao manifesto. A data exibida usa UTC. Quando o projeto ainda estiver apenas no índice local, escolha onde criar seu arquivo `.wna`.

Ao abrir o `.wna`, escolha **Retomar edição salva** para continuar o rascunho ou **Continuar último trabalho** para consultar o último resultado calculado. **Executar e salvar análise de conectividade** oferece a atualização da hipótese quando a configuração difere da revisão aberta. O salvamento do projeto independe do arquivo `.qgz` e das ferramentas de edição de fontes externas.

Antes de fechar ou trocar de projeto, o complemento pede uma decisão se houver alterações pendentes. Conclua editores de complementos, decisões de auditoria e preparações de outros módulos nas respectivas telas. Se uma referência a resultado estiver indisponível, localize o GeoPackage em **Meus trabalhos** antes de salvar.

## Origens e conexões

Em **Investigar minha rede → Analisar conectividade**, abra **Origens de abastecimento** para cadastrar as fontes. Em **Conexões e continuidade da rede**, filtre por categoria e use o menu da linha para conferir a ligação. **Confirmar e incluir na hipótese** grava a interpretação e a situação de acompanhamento e marca a relação no rascunho. **Confirmar sem incluir** registra a mesma interpretação para uso posterior. **Manter separadas** pode participar da hipótese para impedir a inferência daquela união, quando as portas conferem com a rede analisada.

Clique para consultar os detalhes e use o duplo clique para aproximar. A participação, o acompanhamento e a interpretação são gravados separadamente. A revisão de uma relação permanece disponível às hipóteses históricas que a utilizaram.

## Desenhar uma tubulação

Em **Conexões e continuidade da rede**, clique em **Criar tubulação de interligação…**. Escolha no mapa o ponto de saída e o de chegada, nas tubulações conhecidas. Use **Adicionar bends**, **Mover selecionado**, **Remover selecionado** ou **Desfazer último** para ajustar o percurso. Botão direito conclui a captura de bends e Esc a cancela. O ajuste opcional usa a configuração de snapping do QGIS.

Informe apenas os atributos conhecidos. Marque a participação da proposta na hipótese e salve. As duas portas escolhidas determinam sua ligação à rede. O complemento informa se a tubulação vinculada ou a posição gravada divergir numa nova execução. Uma divisão intermediária cria segmentos virtuais vinculados ao Pipe de origem.

**Exportações → Prévia de Pipes e Junctions em GeoPackage…** materializa os segmentos e os nós da execução selecionada. O relatório inclui CRS, unidades, ligações, divisões, IDs originais e divergências entre coordenadas de pontas e nós. A saída destina-se à conferência da topologia no QGIS. A configuração de importação final para ModelBuilder pertence à etapa seguinte.

## Blocos de abastecimento

Na ferramenta **Redes estruturantes**, abra **Mapa de blocos de abastecimento · conectividade GIS**. Escolha as fontes na configuração da execução e calcule os blocos. O nível detalhado separa componentes biconexos por arestas. O nível macro agrupa pontes consecutivas entre bifurcações, entradas de malhas e origens. Ambos preservam a conectividade da fotografia.

Use os filtros por fonte, corredor e áreas. A associação a áreas decorre da interseção com os segmentos e ocorre após a análise da rede global. **Testar origem indisponível** mostra quais origens remanescentes continuam alcançáveis pelos blocos. Distâncias são percorridas no grafo em metros. Quando o orçamento do cálculo for atingido, o acesso global permanece disponível e parte dos percursos detalhados fica em aberto. A função de abastecimento hidráulico exige análise fora deste complemento.

Use o menu da linha para destacar um percurso ou exportar um bloco. É possível exportar os blocos filtrados em GeoPackage, Shapefile ou CSV com as relações e a identidade da execução. **Comparar trabalhos** apresenta alterações nos blocos quando os dois trabalhos tiverem essa análise.

## Salvar projeto como

- **Cópia independente** gera uma nova identidade de projeto e remapeia as execuções de conectividade e investigações estruturais da cópia. Trabalhos de outros tipos exigem copiar o projeto com o mesmo UUID em modo portátil.
- **Mover projeto** torna a nova localização a referência ativa. A pasta anterior fica disponível para recuperação.
- **Pacote portátil** conserva a identidade original. É possível incluir as fontes locais GeoPackage, Shapefile, GeoJSON e FlatGeobuf. Fontes de outros provedores e arquivos indisponíveis ficam registrados como dependências externas.

Os manifestos anteriores continuam legíveis. Projetos que usam os novos tipos de complemento e de resultado devem ser revisados na 1.18.0. Para retorno à 1.17.2, use o manifesto e os bancos anteriores à edição.
