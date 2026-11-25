# Conectividade GIS com seleção no mapa — 1.16.1

A versão 1.16.0 já calculava componentes, candidatas a conexão e alcance topológico de origens sem depender de polígonos ou de um modelo WaterGEMS. A investigação mostrava resumos em listas, a escolha das tubulações dependia da busca por identificador e o mapa só exibia destaques temporários. As hipóteses guardavam o UUID de cada relação participante, sem fixar sua revisão.

## Investigar e revisar no QGIS

1. Abra o projeto `.wna` e vá a **Investigar minha rede → Analisar conectividade**. Selecione as redes, confira o CRS métrico e execute a análise.
2. Em **Definir fontes de água e conexões**, escolha uma origem cadastrada ou posicione uma origem complementar. Use **Selecionar tubulações no mapa** para vincular um ou mais pontos da rede. Clique com o botão direito para concluir ou pressione Esc para restaurar os vínculos iniciais da seleção. Uma lista identifica as feições quando há sobreposição. A busca tabular continua disponível.
3. Na lista de resultados, escolha uma categoria. Clique no cabeçalho de uma coluna para ordenar e use a busca para filtrar por identificador, situação ou região. A tabela exibe até 200 linhas por página. **Mapa e legenda** reúne as ações de consultar, revisar, destacar e aproximar.
4. Em **Decisões e acompanhamento**, registre a situação e, se desejar, uma observação. Para editar a interpretação de uma candidata, use **Revisar conexão selecionada**. Uma conexão confirmada só participa mediante sua inclusão na hipótese executada. O histórico da situação pode ser consultado separadamente.
5. Em **Hipóteses e reexecução**, selecione uma revisão salva ou use **Reexecutar análise com estas alterações** para atualizar a hipótese, criar outra ou experimentar uma configuração temporária. Uma execução temporária ganha seu próprio resultado, sem criar uma revisão de hipótese. **Comparar duas execuções** confronta fotografias persistidas e localiza as diferenças selecionadas no mapa.

**Verificar travessias e limites** examina encontros geométricos com polígonos cadastrados. **Analisar conectividade** trabalha sobre as tubulações do escopo e pode ser executado sem polígonos. O diâmetro mínimo sugerido de 200 mm é um critério ajustável de destaque e priorização. O maior componente é identificado por extensão. O acesso a uma origem depende das relações da hipótese.

## Símbolos e visibilidade

O grupo **WATER NETWORK AUDITOR — MODELO GIS** reúne fontes, conexões e interpretações, vínculos topológicos, componentes e diagnósticos. A árvore de camadas permite controlar a visibilidade de cada categoria. Essas escolhas são cartográficas.

| Referência | Como aparece |
|---|---|
| Origem cadastrada e habilitada | Triângulo ciano |
| Origem complementar habilitada | Pentágono verde-azulado |
| Origem a confirmar | Losango âmbar |
| Origem proposta ou hipotética | Marcador com contorno tracejado |
| Origem fora da hipótese | Triângulo cinza com contorno pontilhado |
| Conexão confirmada | Círculo verde preenchido |
| Conexão declarada | Quadrado azul |
| Conexão candidata | Losango âmbar |
| Sem conexão | Marca cinza em X |
| Proposta ou hipótese de conexão | Círculo com contorno tracejado |
| Conexão indeterminada | Hexágono violeta |

Um vínculo com origem afastada é desenhado entre o equipamento e a posição declarada na rede. A linha tracejada é uma referência de associação. Uma confirmação em T pode dividir virtualmente a aresta receptora no grafo. A interpretação descreve a hipótese topológica adotada pelo usuário. Pressão, vazão, disponibilidade operacional e execução de intervenção física ficam fora desse resultado.

## Persistência e manutenção

- `mapa_topologia_gis.py` reutiliza camadas vetoriais gerenciadas por projeto. Os símbolos são reconstruídos a partir dos GeoPackages e das revisões referenciadas pelo `.wna`. As camadas gerenciadas são de memória. Preserve o manifesto e suas bases para reabrir a representação em outra sessão.
- `hipoteses_gis.py` fixa a revisão do Modelo GIS, os parâmetros, a versão do algoritmo, o conteúdo das entradas e as revisões de cada origem e conexão. Quando os dados deixam de corresponder, a reexecução exata exige restaurar as fontes ou gravar outra revisão. Execuções antigas continuam consultáveis.
- Os GeoPackages da 1.16.0 conservam seu esquema. Hipóteses antigas com referências apenas por UUID precisam de uma revisão explícita para que futuras reexecuções fixem as participações. As execuções antigas preservam os participantes efetivamente usados.
- A comparação usa a identidade técnica das tubulações. Uma geometria ou atributo de identidade alterado pode aparecer como retirada e inclusão. A mudança de conectividade junto a uma relação revisada é uma associação observada na comparação.
- A análise de conectividade reutiliza o motor da Etapa 2. A interface lê os elementos com os filtros do Modelo GIS e calcula os resultados em tarefas acompanháveis. Os destaques no mapa são temporários.

## Desempenho observado

Ensaio sintético com o Python do QGIS 3.44.15 no Windows 11, 31.250 tubulações e 15.875 nós, três repetições por versão na mesma estação. A medição cobre a construção do grafo, com uma origem, sem renderização do mapa ou escrita do GeoPackage.

| Versão | Mediana | Pior execução |
|---|---:|---:|
| 1.16.0 | 7,80 s | 8,10 s |
| 1.16.1 | 7,99 s | 8,20 s |

Os ensaios do complemento instalado usam redes e origens sintéticas. A validação operacional do cadastro é feita separadamente no projeto do usuário.
