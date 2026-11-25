# Redes estruturantes GIS · 1.17.0

A análise usa nós, arestas, divisões virtuais, origens e conexões de uma execução de **Analisar conectividade**. O grafo GIS é não dirigido. Os resultados descrevem a conectividade sob as regras e relações registradas naquela execução. O módulo funciona sem um modelo WaterGEMS.

## Executar no QGIS

1. Abra o projeto `.wna` no complemento. Em **Investigar minha rede → Analisar conectividade**, abra ou gere uma execução com as fontes e conexões pertinentes.
2. Use **Redes estruturantes** nessa execução. O comando também está disponível entre os objetivos de **Investigar minha rede**. Nesse caso, selecione a execução desejada na lista.
3. Em **Execução, fontes e destinos**, mantenha marcadas as origens que devem participar. A lista contém somente as origens habilitadas com vínculos válidos na execução. Uma origem complementar pode estar longe da tubulação e usa os pontos de ligação gravados.
4. Para estudar a rede inteira, deixe a lista de destinos vazia. Para estudar pontos de alimentação, escolha **Nó topológico** ou **Tubulação**, clique no mapa e conclua com o botão direito. A seleção de um Pipe usa o nó da parte clicada mais próximo da posição escolhida ao longo da linha.
5. Para estudar uma área, adicione as tubulações por interseção espacial ou selecione destinos e use **Vincular destinos selecionados à área e salvar revisão**. A associação declarada e o recorte espacial ficam identificados separadamente. Se necessário, recupere uma revisão anterior na mesma execução.
6. Use **Calcular e salvar análise estrutural**. Escolha a categoria de resultado, filtre pelo ID, área ou origem e clique em uma linha para ler os detalhes. Duplo clique aproxima e destaca. O botão direito abre ações para o registro. Clique no cabeçalho para ordenar e use seu menu para ajustar as colunas visíveis.
7. Use **Mostrar camadas** para consultar o grupo de resultados na árvore do QGIS e controlar a visibilidade de cada categoria. As camadas geradas usam as geometrias da fotografia, com simbologia própria. Use **Limpar** no painel para remover o destaque temporário.

Sem origens selecionadas, a análise inventaria pontes e articulações. A interpretação de alcance a origens fica indeterminada. Sem destinos, os impactos dos cortes continuam disponíveis para a rede inteira.

## Ler os resultados

| Resultado | Evidência utilizada |
| --- | --- |
| Ligação crítica | A retirada do Pipe físico elimina o acesso a todas as origens selecionadas para pelo menos um Pipe remanescente ou destino anteriormente alcançável. |
| Ponte | O segmento separa o componente em duas partes quando retirado. Pode haver uma origem em cada parte. |
| Articulação | Nó cuja retirada separaria o componente. A lista identifica o nó para inspeção. |
| Corredor | Trecho em um trajeto calculado entre origem e destino. O trajeto de referência usa comprimento geométrico acumulado. |
| Redundância | O cálculo encontrou outra rota da mesma origem sem compartilhamento de nenhum Pipe físico com a rota de referência. Alternativas que compartilham Pipe são exibidas como parciais. |
| Rede de passagem | Um trecho usado na rota a uma área com destino declarado atravessa o polígono de outra área. |
| Distribuição local observada | Trecho da rota que tem extensão dentro da área do destino declarado. Pode coexistir com rede de passagem e criticidade. |
| Função indeterminada | A informação disponível é insuficiente ou o cálculo daquele corte agrupado excedeu o limite de trabalho. |

O indicador de comprimento afetado soma somente arestas remanescentes que perderam acesso a todas as origens. O Pipe retirado e trechos que já estavam sem acesso ficam fora dessa soma. A contagem global usa a identidade cadastral da feição uma vez, inclusive em Pipes divididos virtualmente. Quando os indicadores são apresentados por componente, cada componente mostra suas partes. O diâmetro aparece em milímetros se a unidade estiver confirmada na execução original.

Uma zona pode incluir destinos que alcançam origens diferentes. A tabela mostra o conjunto de fontes acessíveis e separa as origens exclusivas de algum destino e os destinos alcançáveis apenas por fontes complementares. O alcance e as alternativas são topológicos. Em especial, os resultados não medem vazão, pressão ou capacidade da alternativa. Um cruzamento ou recorte no polígono sozinho tem significado espacial.

## Testar interrupções, comparar e recuperar

- Abra **Testar interrupção topológica** e escolha um ou vários Pipes no mapa. Também é possível incluir um Pipe pelo menu da tabela. A ferramenta retira do cálculo todas as arestas de cada Pipe escolhido. Os resultados mostram componentes, origens remanescentes, destinos retirados diretamente, destinos que perderam acesso e rotas remanescentes. **Salvar resultado da interrupção** cria um trabalho vinculado ao anterior.
- Para **Comparar trabalhos**, salve investigações em duas execuções, hipóteses ou seleções de origens do mesmo projeto. A comparação usa as identidades persistidas para mostrar alterações de função e impacto, origens, conexões aplicadas, dependências de destino e rotas. Identidades diferentes aparecem como novas, ausentes ou em outro escopo. Uma área sem destino em um dos trabalhos fica sem comparação conclusiva de acesso.
- Em **Meus trabalhos**, filtre por **Redes estruturantes GIS** para abrir trabalhos e interrupções. O manifesto `.wna` referencia cada GeoPackage novo. O resultado inclui a fotografia usada e reabre sem recalcular a rede. As bases e fontes originais permanecem em seus caminhos.
- Use **Conferir dados atuais das fontes** para comparar o conteúdo das camadas com a assinatura original. Divergência no cadastro ou no conteúdo indica a necessidade de gerar nova execução para estudar a rede atual. Fotografias históricas continuam disponíveis.
- **Exportações** gera GeoPackage ou Shapefiles em uma nova pasta, acompanhados das tabelas CSV e do JSON com origem, versão do algoritmo, critérios, associações e eventual interrupção.

## Implementação e limites

A 1.16.2 já persistia o grafo resolvido com arestas indexadas por parte e portas identificadas por posição no trecho. A 1.17.0 consome esse contrato em `dependencias_gis`, `corredores_gis` e `representacao_estrutura_gis`. A busca em profundidade iterativa distingue arestas paralelas e usa intervalos de subárvore para avaliar pontes sem uma varredura por Pipe. A contagem de feições distintas usa uma árvore de Fenwick. A retirada de Pipe com várias arestas usa busca exata dentro de um orçamento de 4 milhões de unidades de trabalho, estimado por nós, arestas e destinos. Cortes individuais fora do orçamento podem ser testados explicitamente pelo usuário.

O alcance às origens é calculado por componentes, preservando portas separadas da mesma origem. O cálculo detalha uma rota a partir da origem mais próxima por comprimento e, conforme o orçamento, rotas específicas para até quatro origens. Para verificar a independência, a busca exclui todos os Pipes da rota de referência de uma vez. Um ensaio adicional pode comprovar uma alternativa parcial. Se a rota escolhida não tiver alternativa disjunta, podem existir outros pares de trajetos independentes. O módulo limita as buscas adicionais e a quantidade de segmentos armazenados, e indica os destinos e origens sem detalhamento. Após um corte explícito, conserva o alcance de todos os destinos e detalha trajetos para até 250 deles, dentro do limite total de segmentos.

O grafo da 1.16.2 guarda os nós já unidos. Por isso, a passagem por um nó com conexão declarada aplicada é registrada como evidência da rota. A dependência de uma única relação pode ser investigada comparando duas hipóteses que diferem nessa ligação. A análise também conserva a indicação de destinos por interseção espacial e usa polígonos apenas quando fornecidos.

Cálculo, leitura e exportação têm tarefas canceláveis. A geometria cartográfica é publicada no QGIS mediante ação do usuário. Projetos com muitas feições podem levar mais tempo para exibir as camadas temáticas. A análise executa sobre o comprimento e as geometrias já registrados, com o CRS métrico usado na conectividade.

## Reproduzir a validação

Use a versão Python do QGIS para rodar a suíte e medir os grafos sintéticos.

```text
python testes/executar_suite_isolada.py resultados/suite_1_17_0
python testes/medir_estrutura_gis.py resultados/desempenho_1_17_0.json
```

A medição usa redes malhada e ramificada, cada uma com 32.400 nós, 2 origens e 25 destinos. Ela mede o cálculo sobre o grafo resolvido e o corte de dois Pipes em cinco repetições. A memória corresponde ao pico de alocações Python em uma execução separada. Inclua tempo de construção de topologia, I/O e renderização à parte em comparações de ambiente.
