# Investigações, revisão de conexões e cadastro para modelagem

## No QGIS

1. Abra o projeto `.wna`. A abertura oferece **Continuar último trabalho**, **Abrir análise salva** e **Iniciar nova investigação**. A escolha recolhe esse painel. **Salvar projeto** continua no cabeçalho.
2. Abra **Investigar minha rede**. O seletor reúne **Verificar travessias e limites**, **Analisar conectividade**, **Redes estruturantes e blocos de abastecimento** e as ferramentas GIS–WaterGEMS. Em redes estruturantes, escolha a análise de conectividade pelo nome, hipótese, revisão e data. Na falta de uma análise, use o acesso à conectividade e retorne à escolha da referência.
3. Defina as origens e a área de interesse na configuração compartilhada. A comparação de duas origens gera referências individuais na visão integral. O subconjunto analisa o alcance das fontes escolhidas em conjunto. Os polígonos qualificam os destinos ou a apresentação. O cálculo continua sobre a fotografia completa.
4. Escolha **Visão macro integral**, **Percursos até destinos específicos** ou **Criticidade e interrupções**. No modo combinado, os destinos manuais têm precedência e são completados automaticamente até o limite. A visão macro considera toda a rede alcançável, inclusive sem destinos específicos.
5. Em **Mapa, árvore e exportação**, renderize os corredores em cor única ou por corredor. A espessura inicial é 1,00 mm e os corredores têm prioridade de desenho acima dos blocos. As preferências de mapa são recuperadas com a análise. **Verificar se o cadastro GIS mudou** mostra o resultado por fonte. Em fotografias antigas com assinatura agregada, uma diferença pode ficar inconclusiva para fontes individuais.
6. Em **Meus trabalhos**, pesquise pelo nome, filtre pela hipótese ou ordene pela data. Use o menu de uma análise para consultar parâmetros ou mudar o nome de apresentação. Os GeoPackages e seus identificadores permanecem intactos.

## Revisar conexões

Em **Analisar conectividade → Conexões e continuidade da rede**, abra **Revisar conexões em sequência**. Use categoria, componente, área, pendência ou seleção das tabelas para iniciar a fila. A revisão destaca a posição e os Pipes relacionados. **Confirmar e incluir**, **Confirmar sem incluir**, **Manter separadas** e **Necessita investigação** gravam revisões e avançam. A interpretação **Manter separadas** pode participar da hipótese como restrição à inferência. **Pular por enquanto** avança sem gravar decisão.

Use **Retomar revisão salva** após abrir a mesma análise de conectividade. A fila, seu cursor e o rascunho vinculado são separados da fotografia. Um rascunho mais recente pode exigir recuperação ou escolha explícita. Aplique as decisões em uma nova execução. **Adicionar conexão entre tubulações** declara uma ligação topológica. **Criar tubulação de interligação** registra uma intervenção com geometria, vértices intermediários, atributos e portas.

## Exportar

**Exportar dados GIS para modelagem → Prévia do cadastro completo** concilia o Modelo GIS atual com a análise de referência. Confira as contagens, a atividade pretendida, as fontes lidas e as pendências. Pode-se editar a atividade por Pipe físico e salvar a preferência. O GeoPackage registra camadas de Pipes e Junctions e as tabelas de inventário, procedência e operações topológicas. Shapefile acompanha tabelas e dicionário dos campos.

Exportações de corredores, blocos, áreas e percursos continuam disponíveis nos respectivos contextos. **Exportar resultados da investigação** gera as tabelas de diagnóstico separadamente.

## Diagnóstico da 1.18.1 e limites

A entrada anterior separava **Analisar conectividade** do seletor principal e repetia a entrada estrutural dentro da conectividade. Havia listas diferentes para as mesmas origens e áreas, e os resultados de métodos distintos dividiam um único seletor extenso. A 1.18.2 mantém uma entrada para cada ferramenta e reutiliza a mesma configuração de escopo nas modalidades estruturais.

A prévia usa as conexões e divisões da fotografia. Extremos de Pipes sem topologia resolvida recebem Junctions independentes para conferência. Equipamentos são preservados no inventário com a categoria e vínculos conhecidos. A configuração hidráulica e a importação no ModelBuilder ficam para a etapa seguinte. O [contrato técnico](CONTRATO_MODELBUILDER_1_19_0.md) explica essas regras.
