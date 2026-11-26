# Contrato de preparação GIS para o ModelBuilder

## Escopos e integridade

| Escopo | Origem | Regra |
| --- | --- | --- |
| Cadastral | Fontes de tubulação, Junctions e equipamentos cadastradas na revisão do Modelo GIS | Para Pipes, as expressões usadas na análise deixam de restringir a leitura da prévia. O subconjunto do provedor continua vigente e aparece como limitação. |
| Hipótese | Fotografia de conectividade escolhida e participantes com revisões fixadas | A correspondência entre partes usa a identidade técnica. Propostas materializadas precisam constar como aplicadas na fotografia. |
| Alcançável | Busca no grafo resolvido a partir das origens selecionadas | Alcançável, sem origem ou indeterminado. A condição permanece independente da atividade pretendida. |
| Exportável | Escopo escolhido para a saída | Pode conter todo o cadastro visível, rede alcançável, corredores, blocos ou percursos. A seleção do escopo não modifica a hipótese. |

O manifesto identifica fontes ausentes, subconjuntos do provedor, geometrias descartadas, lacunas de correspondência e diferenças entre ponta geométrica e nó topológico. As coordenadas são expressas no CRS projetado e métrico validado da análise. O comprimento geométrico é expresso em metros. O diâmetro requer mapeamento e unidade declarados. Um atributo ausente permanece pendente.

## Identidades e transformações

Cada linha de `pipes` preserva o identificador técnico do segmento, o Pipe original, a parte, os intervalos fracionários, o identificador cadastral bruto e os nós inicial e final. O inventário preserva `ID_GIS`, inclusive repetições, nulos e zero, Label, fonte, camada e atributos originais. O identificador de um segmento deriva da parte e do intervalo ordenado. A entidade física é contabilizada separadamente de suas partes virtuais. A fotografia resolve todas as divisões aplicadas antes da materialização. A geometria inteira do Pipe dividido permanece representada no inventário por referências e atributos.

O manifesto registra as posições de divisão. As tabelas `operacoes_topologicas` e `portas_junction` conservam as relações declaradas, os complementos participantes, as portas e as revisões. Um vínculo declarado que une coordenadas diferentes conserva a divergência como pendência. O exportador só materializa um Pipe adicional quando houver uma intervenção explícita aplicada. Trechos que não estavam na hipótese recebem nós próprios nas extremidades. A eventual continuidade desses trechos pode ser analisada em outra execução.

Procedência, situação cadastral, participação, condição topológica e atividade são campos independentes. Para atividade, os estados são **ATIVO**, **INATIVO** e **A_DEFINIR**. O padrão é **A_DEFINIR**. A regra explícita pode definir como ativos os Pipes da hipótese ou como inativos os Pipes de fora dela. Uma decisão por Pipe prevalece sobre a regra. As divisões virtuais herdam a decisão do Pipe físico. Reservatórios, tanques e demais equipamentos aparecem no inventário como candidatos a mapeamento por tipo.

## Mapeamento a validar na 1.19.0

| Entidade | Dados GIS disponíveis | Validação no WaterGEMS |
| --- | --- | --- |
| Pipe | Geometria, comprimento, diâmetro, material, nós associados, chave de segmento e rastreabilidade do Pipe original | Configurar campo-chave, Start/Stop Node, unidades e atualizações. Revisar rugosidade e valores obrigatórios ausentes. |
| Junction | Geometria, chave, portas e procedência | Conferir associação aos nós, tolerância e tratamento de duplicidades. Cotas e demandas dependem de fontes válidas. |
| Reservoir, Tank e entrada | Categoria GIS, geometria quando disponível e vínculo declarado | Confirmar tipo, níveis, cotas e condições de operação. |
| Bomba, booster e tipos de válvula | Inventário por tipo, atributos existentes e referências quando conhecidas | Confirmar tipos nativos, modo de ligação e dados de operação. Curvas, regulagens e estados operacionais ficam pendentes quando faltarem. |
| Atividade pretendida | Estado, regra aplicada e exceções por Pipe | Testar se o ModelBuilder da versão em uso permite alimentar a alternativa de Active Topology. Manter a correspondência externa para eventuais aplicações manuais. |

Para importar ou atualizar, registrar uma tabela de correspondência entre UUID do projeto, identidade técnica e identificador efetivamente atribuído no WaterGEMS. Em identificadores repetidos ou ausentes, manter o valor bruto e utilizar uma chave de importação única. Quando uma edição de atributos ou de geometria alterar o identificador técnico, conciliar a identidade com a versão anterior antes de atualizar. Uma igualdade de nome ou de geometria aproximada exige revisão. Para substituir um Pipe dividido, revisar a transição do Pipe anterior para os novos segmentos e seus nós. A importação deverá ser repetível sem criar uma segunda cópia dos elementos já conciliados. Validar tudo em cópias de projeto e modelo.
