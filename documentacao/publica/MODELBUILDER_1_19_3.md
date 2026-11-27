# Resolução de conexões conflitantes no ModelBuilder

Na 1.19.2, o assistente misturava diagnósticos da última validação com registros gravados em revisões anteriores. A 1.19.3 forma a fila com as pendências críticas da configuração validada. Decisões, execuções em espera e correções já confirmadas ficam disponíveis no histórico.

## Resolver uma ocorrência

1. Abra o projeto `.wna` e uma execução de conectividade de hipótese salva. Em **Investigar minha rede**, abra **Exportar modelo para WaterGEMS**.
2. Na última etapa, use **Validar** e abra **Corrigir pendências**. Escolha o Pipe e clique em **Resolver conexões conflitantes**.
3. Confira as ligações A, B e demais relações. Clique numa linha para ver os Pipes e as posições e destacar essa ligação no QGIS. Use **Histórico da ligação** para comparar a revisão da fotografia com as revisões gravadas. **Revisar referência ou posição no mapa** permite indicar outra porta explicitamente.
4. Escolha quais ligações manter, deixar fora da hipótese ou registrar como **Sem conexão**. Para consolidar ligações que representam o mesmo ponto físico, indique a posição principal. Se a informação de campo for insuficiente, use **Manter pendente**.
5. Use **Pré-visualizar decisão**. Confira os segmentos, nós, componentes e referências de equipamentos e conjuntos que podem precisar de revisão.
6. Clique em **Salvar decisões e recalcular conectividade**. Após a execução, o assistente valida o cadastro completo e volta à fila ou mostra a decisão validada no histórico. Se precisar retomar mais tarde, abra **Histórico e execuções pendentes** no exportador e selecione **Executar hipótese derivada**.

Deixar uma ligação fora da nova hipótese preserva seu veredito cadastral. O grafo pode manter a continuidade por outro caminho ou por inferência habilitada. **Sem conexão** grava uma nova revisão da relação. Ambas as operações preservam a fotografia e os vínculos da hipótese anterior. A divisão de anéis para o pacote continua disponível como correção de materialização.

## Como interpretar os resultados

- A investigação procura relações ancoradas no intervalo e nas portas topológicas do Pipe. A tabela diferencia presença na hipótese, aplicação pelo motor e incompatibilidades da referência. A indicação de cadeia de ligações só aparece quando as relações aplicadas conectam as duas portas por identidades coincidentes. Uma união por inferência pode depender de outras condições da execução.
- A auditoria reutiliza a comparação de Pipes, posições e interpretações. Registros próximos podem representar ligações distintas. Se as pontas do segmento forem válidas e usarem nós distintos, o segmento curto é preservado.
- A prévia usa os parâmetros e as fontes identificados na execução de referência. Antes de gravar, o complemento confere novamente as revisões. O GeoPackage de complementos recebe as decisões e a hipótese derivada na mesma transação.
- A validação exige que o mesmo trecho físico esteja presente no cadastro completo com Pipes habilitados. Uma exportação com escopo reduzido pode omitir um trecho sem demonstrar resolução. Se volta a existir pendência crítica na mesma parte numa revisão descendente, a fila pode sinalizar reabertura.
- A sinalização de equipamentos e Selection Sets orienta revisão. Uma associação anterior pode precisar ser reconciliada com a nova execução. A operação preserva os bancos WaterGEMS e as fontes GIS.

## Limitações

A derivação assistida requer uma execução salva com revisão de hipótese e assinatura do inventário. Se o cadastro mudar ou a execução for antiga e não contiver essas referências, gere uma nova execução antes de gravar a decisão. Relações direcionais que exigem reposicionamento devem ser revistas no editor de conectividade. Uma relação sem portas identificáveis precisa ser recuperada pelo cadastro ou pelo histórico.

A prévia avalia conectividade topológica. A representação hidráulica e a importação nativa no WaterGEMS dependem de validação no software de destino.
