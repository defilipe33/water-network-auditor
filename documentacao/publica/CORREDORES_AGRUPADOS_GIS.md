# Corredores estruturantes agrupados · 1.17.1

Na 1.17.0, o resultado estrutural registrava a função de cada Pipe, o percurso de cada par origem–destino e a união cartográfica dos segmentos. A 1.17.1 acrescenta uma identidade para cada sequência contínua compartilhada pelos percursos. O agrupamento consome o grafo e as rotas existentes. A criticidade continua sendo calculada pelo impacto do corte do Pipe físico.

## Identificar e consultar

1. No QGIS, abra **Investigar minha rede → Redes estruturantes** e selecione uma execução de conectividade. A tela **Analisar conectividade** também oferece acesso direto à análise estrutural.
2. Marque as origens consideradas. Em **Destinos representativos**, mantenha **Regiões distantes** ou escolha destinos manuais. No modo automático, ajuste o máximo de destinos e a distância mínima pela rede. No modo manual, escolha nós ou tubulações no mapa. Também é possível escolher uma área cadastrada no mapa e associar explicitamente seus destinos.
3. Clique em **Identificar corredores agrupados**. O resultado é salvo como novo trabalho do projeto. A categoria **Corredores agrupados** mostra a função, os Pipes físicos, os diâmetros disponíveis, o comprimento, as origens, os destinos e os vínculos entre corredores.
4. Expanda **Visão macro e árvore de percursos**. Escolha a fonte, o nível e as funções de interesse. **Mostrar camada dos corredores** organiza as geometrias em uma camada gerenciada na árvore do QGIS. A camada utiliza os segmentos registrados na investigação.
5. Na tabela, um clique lê os detalhes e o duplo clique aproxima a extensão integral. Na árvore, escolha um corredor para destacá-lo ou um destino para ver seu percurso completo. O menu contextual também permite consultar Pipes, destacar ramificações, escolher um percurso e exportar.
6. Em **Meus trabalhos**, reabra a análise pelo projeto `.wna`. As investigações da 1.17.0 continuam legíveis. **Agrupar trajetos deste trabalho** grava uma nova investigação com as rotas existentes, quando disponíveis. O comando principal permite calcular novos destinos na mesma fotografia.

O quadrado verde e o losango laranja indicam os extremos da sequência. A cruz roxa marca uma ramificação. Linhas exclusivamente alternativas aparecem tracejadas. A orientação dos extremos da sequência é cartográfica. O percurso ordenado segue a origem e o destino considerados.

## Como a amostra e o agrupamento funcionam

**Destinos automáticos.** Uma busca Dijkstra multiorigem calcula a menor distância acumulada pela rede à origem alcançável mais próxima. As folhas da floresta resultante oferecem candidatos mesmo em redes malhadas. O máximo de destinos define a largura de faixa usada para agrupar folhas com ancestral comum. A largura corresponde à maior distância alcançável dividida pelo máximo escolhido, limitado ao intervalo de 3 a 12 faixas. Pontas curtas irmãs agrupam-se pelo nó pai mesmo na transição entre faixas. Em cada grupo, vence a folha mais distante, com preferência por extremidade física no empate e desempate pelo UID do nó. A seleção tenta representar uma folha por raiz ativa antes de usar as vagas restantes. Os parâmetros, a distância e a contagem de candidatos ficam salvos.

**Corredores e percursos.** A união das rotas de referência e alternativas é particionada nos nós de ramificação e nos pontos onde muda a participação em percursos. Cada segmento da união pertence a um corredor. O mesmo Pipe original pode aparecer em corredores diferentes quando suas partes virtuais são usadas por rotas diferentes. Um percurso preserva a sequência dos corredores e pode referenciar os mesmos agrupamentos de outros percursos.

| Função | Critério |
| --- | --- |
| Tronco compartilhado | A sequência participa de dois ou mais percursos de referência. |
| Ramal alimentador | A sequência participa de um percurso de referência. |
| Corredor terminal | Um extremo da sequência corresponde a um destino de referência. |
| Corredor alternativo | A sequência participa de uma alternativa registrada. |
| Corredor crítico | A sequência inclui um Pipe cujo corte individual compromete o acesso de um destino relacionado a todas as origens consideradas. |
| Função indeterminada | Faltam origens ou evidências suficientes para atribuir função. |

Os vínculos anteriores e posteriores decorrem da ordem dos percursos de referência ou alternativos. A árvore agrupa prefixos por origem e pode mostrar a mesma identidade em mais de um ramo. Sem origens definidas, o resultado apresenta cadeias por continuidade e circuitos fechados, com componentes sem ligação mantidos separados. Essa vista fica sem percursos orientados.

**Níveis de visualização.** Resumido mostra até o primeiro terço dos destinos, com prioridade à distância dos percursos. Intermediário mostra até dois terços. Detalhado mostra todos os corredores identificados. Os filtros de fonte e função e a opção de ocultar ramais secundários servem para navegar e desenhar a camada. A árvore pode exibir os demais trechos de um percurso filtrado para preservar o contexto. Os níveis conservam o resultado salvo, as origens e a topologia.

## Exportar um corredor ou percurso

No menu da linha, use **Exportar corredor selecionado** ou **Exportar percurso completo**. Escolha GeoPackage, Shapefile ou CSV com relações. Os formatos espaciais abrem no QGIS e acompanham tabelas CSV e metadados JSON. Cada exportação recebe uma pasta própria.

- **Segmentos efetivamente usados** exporta uma feição por trecho usado, inclusive recortes de divisões virtuais. A tabela guarda ordem, nós, frações, identidade do corredor, UID do Pipe, ID cadastral, parte, camada, fontes GIS, comprimento e diâmetro validado quando disponível.
- **Pipes físicos completos** exporta uma feição por Pipe, com todas as suas partes originais. A tabela de relações conserva a sequência de segmentos e as posições correspondentes de cada Pipe no percurso.

**Renomear corredor** anexa uma revisão vinculada ao UUID do corredor. **Histórico de nomes** conserva o nome original e as alterações. A exportação usa o nome vigente.

## Alcance da interpretação

Os caminhos são percursos topológicos de referência. A amostra privilegia destinos distantes e usa os limites do cálculo estrutural da 1.17.0. A lista de fontes alcançáveis pode ser mais ampla que a lista de rotas detalhadas. Uma alternativa parcial pode compartilhar trechos com a rota de referência. A ausência de uma alternativa detalhada pode decorrer do orçamento ou da estratégia de busca. A tabela distingue esses estados. A interseção com uma zona tem significado espacial, e o pertencimento hidráulico requer evidência própria.

As medições do cálculo são reproduzíveis com o Python do QGIS. O ensaio usa malha e rede ramificada sintéticas com 32.400 nós cada.

```text
python testes/medir_estrutura_gis.py resultados/desempenho_1_17_1.json --agrupado
python testes/executar_suite_isolada.py resultados/suite_1_17_1
```
