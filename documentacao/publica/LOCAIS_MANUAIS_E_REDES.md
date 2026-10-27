# Locais manuais e conjuntos de redes — 1.6.0

## Uso no QGIS

Abra uma investigação integrada persistida. Em DIAGNÓSTICOS, use **Adicionar
local** e clique no mapa; Esc cancela a captura. Ou selecione elementos de fontes
identificáveis e use **A partir da seleção**. Nesse caso, a posição inicial é o
centroide das geometrias selecionadas disponíveis no CRS da auditoria. Pode ser
ajustada antes de salvar. Não é necessário existir um evento automático.

Título, classificação livre e observação são opcionais. Localizar candidatos
próximos usa raio em metros e transformação explícita de CRS. Marque os elementos
desejados; nenhum candidato é associado apenas pela distância. A busca por
identificador também funciona independentemente da proximidade, limitada a 300
candidatos por consulta. Refine a busca quando necessário. Geometrias WaterGEMS
continuam bloqueadas quando sua referência espacial não estiver validada.

As fontes GIS são reconhecidas por provedor, URI e assinatura de atributos + WKB.
Feições idênticas ambíguas e fontes duplicadas não são escolhidas arbitrariamente.
É possível consultar um ponto sem fontes originais, com os dados preservados.
Selecionar fontes ausentes não é possível. A lista distingue origem automática e
manual; os dois registros nunca são fundidos por proximidade.

**Editar local manual** altera título, classificação, observações, coordenadas e
vínculos. Antes de mover um ponto com associações, há confirmação de conferência
dos vínculos: eles não são recalculados silenciosamente. Alterar posição ou
composição abre novo contexto de análise, mantendo a UUID do local. Alterar só
texto conserva o contexto. O formulário de resultado continua sem responsável,
documento ou aprovação obrigatórios. Histórico e vínculos são consultáveis no
detalhamento e nas exportações.

Em CONFIGURAÇÕES E FONTES, **Excluir logicamente** retira da lista ativa sem
apagar histórico. **Restaurar local manual excluído** permite retomá-lo. A camada
própria de locais manuais usa losangos, no grupo da investigação; não muda os
estilos de eventos, locais automáticos ou dados originais. A seleção de um único
ponto pode atualizar o painel se o caso estiver na lista filtrada. O zoom permanece
explícito.

## Atualizações e recuperação

Ao gerar nova investigação pelo controlador, locais manuais da investigação ativa
do mesmo modelo são recuperados conservadoramente. A abertura simples de uma
versão histórica não importa nada. Também existe **Recuperar locais manuais de
outra investigação**: selecione o GPKG anterior. A recuperação prepara e valida uma
cópia temporária, verifica concorrência e publica os novos registros em transação.

O histórico do local anterior é preservado no registro técnico de origem. UUIDs,
assinaturas e identidade do modelo são comparadas. Vínculos WG ausentes, alterados
ou ambíguos permanecem como referências históricas e não entram no grafo nem nos
destaques de elementos atuais. Resultados de análise anteriores não são herdados:
a recuperação pede reavaliação. Fontes GIS e regiões requerem conferência explícita.
Recuperações repetidas da mesma revisão não duplicam locais. As execuções anteriores
permanecem intactas.

## Identificar redes principais

Use **Redes principais…** no painel integrado. A análise usa a base WaterGEMS
persistida da investigação e a perspectiva indicada na janela. Não é necessário
abrir o arquivo hidráulico original.

- **CADASTRAL:** configure antes os filtros genéricos do painel. Cada tubulação é
  avaliada individualmente. Campos GIS só participam quando há correspondência
  inequívoca persistida; atributos ausentes não se tornam falsos nem correspondências.
  As regiões relacionadas usam vínculos técnicos existentes, não seus nomes.
- **TOPOLOGICO:** identifica pontes na projeção não dirigida da perspectiva e/ou
  corredores dirigidos entre reservatórios/tanques e destinos explicitamente
  escolhidos. Bombas não são classificadas como fontes de água. Corredores têm
  menor número de arestas, não menor custo hidráulico; empates não demonstram
  unicidade e todos os links paralelos do corredor são apresentados.
- **COMBINADO:** união (OU) ou interseção (E) dos critérios anteriores. Cada linha
  conserva os motivos da inclusão. Não há pontuação hidráulica inventada.

Pontes incluem ramificações e pontas de redes. **Uma ponte não é automaticamente
uma rede principal**, e a ausência de pontes em uma malha não significa ausência de
redes importantes. O maior componente não define o conjunto. A projeção de pontes
mede conectividade fraca e não disponibilidade direcional; corredores respeitam
o grafo dirigido e suas barreiras. ESTRUTURAL inclui elementos inativos conforme
a regra existente; TODAS_VALVULAS_ABERTAS respeita Active Topology e limitações de
bombas/retenções. ESTADOS_DO_CENARIO continua bloqueado.

As métricas da interface usam o **grafo completo da perspectiva**. O filtro cadastral
não recorta silenciosamente o universo das métricas. A API aceita um escopo explícito
de tubulações, registrado no resultado: isso muda as métricas. Não há centralidade
exata de todas as arestas nesta versão. O cálculo reutiliza o worker e o painel de
atividade, com cancelamento cooperativo; o conjunto só é salvo por ação explícita.

Campos físicos WaterGEMS podem estar em unidades internas diferentes das de
apresentação. O filtro indica **unidade bruta da fonte**; confirmar a unidade de
diâmetro/comprimento antes de informar um limiar. A validação da unidade das
coordenadas não valida automaticamente as unidades de todas as propriedades.
Não digite um valor em mm em um campo bruto sem verificar sua unidade. Não são
usados vazão, velocidade, pressões ou sentido de escoamento.

Desmarque linhas para retirar tubos e use **Acrescentar selecionadas** para incluir
tubulações da versão identificável. **Carregar seleção QGIS** cria representação
própria, selecionada, sem modificar as fontes. Salve um nome livre. Salvar de novo
gera revisão do mesmo conjunto; um conjunto novo não substitui outro pelo nome.
Critérios originais, inclusões e remoções manuais ficam registrados. Recuperar e
Comparar permitem examinar conjuntos anteriores. Rascunhos são protegidos por
Salvar/Descartar/Cancelar.

## Selection Set no WaterGEMS

O CSV exportado contém DomainElementID, Label textual, tipo, UID, modelo, cenário,
versão, perspectiva, UUID do conjunto e origem da inclusão. Nomes repetidos são
avisados; elementos ausentes ou com identidade divergente bloqueiam a exportação.
Abra o CSV por importação de texto para preservar zeros à esquerda no Excel.
Não sobrescreve arquivos existentes.

O CSV **não é um Selection Set nativo nem uma importação direta comprovada**.
A Bentley documenta criar conjuntos a partir de seleção, consultas ou FlexTables
filtradas. Procedimento de conferência na instalação utilizada:

1. Abra uma cópia do modelo correspondente à identidade e versão exportadas.
2. Em Queries, crie consulta do tipo Pipe usando os IDs da lista (ou Labels somente
   quando únicos), conforme a sintaxe disponível na versão instalada.
3. Selecione o resultado, confira contagem, tipos e uma amostra de IDs/Labels.
4. Use Create Selection Set na seleção; alternativamente, na FlexTable filtrada,
   Options → Create Selection Set. Dê um nome e confira os membros.
5. Salve a cópia do modelo apenas por ação consciente no WaterGEMS. Este complemento
   não escreve Selection Sets no SQLite nem gera intervenções aprovadas.

Referências oficiais: [criar Selection Set](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015896)
e [listas de planilha e consultas](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0059255).
As instruções da segunda referência são para versões antigas; conferir menus e
sintaxe na versão instalada antes do uso operacional. A criação nativa no desktop
WaterGEMS continua pendente de aceitação por amostragem.

## Persistência e exportações

Extensão aditiva **IGD_CONJUNTOS_SCHEMA**, versão 2, no mesmo GeoPackage integrado,
com backup completo verificado antes da instalação/migração:

| Tabela | Papel |
|---|---|
| IGD_OBJETOS | UUID e execução proprietária; local manual ou conjunto |
| IGD_OBJ_HIST | Revisões encadeadas, versão WG, perspectiva, dados e exclusão lógica |
| IGD_OBJ_VINCULOS | Uma linha por elemento por revisão, origem e natureza da associação |
| IGD_MANUAL_GEOM | Geometria por revisão no CRS da auditoria; chave permanente hist_uid |
| IG_MANUAIS_ATUAIS | Visão espacial dos locais ativos mais recentes |

O `fid` é apenas chave do provedor espacial. As identidades permanentes são UUIDs.
Tabelas históricas têm proteção contra UPDATE/DELETE; gravações usam transação e
controle otimista de concorrência. Resultados usam o IGD_ANALISES existente. Mudança
de composição produz contexto próprio; a UUID do local continua consultável.

O acompanhamento XLSX/CSV inclui LOCAIS_MANUAIS, CONJUNTOS_REDES, vínculos e
histórico. Dados técnicos extensos são divididos em DADOS_OBJETOS_PARTES, até
30.000 caracteres por parte, sem truncamento; concatenar por HIST_UUID e PARTE.
GPKG conserva a base completa. SHP de acompanhamento representa ocorrências
espaciais, incluindo os pontos manuais; relacionamentos ficam nas tabelas auxiliares.

## Aceitação manual

No QGIS 3.44.15 instalado, em perfil de teste: criar ponto sem evento, escolher
candidatos, salvar observação, alterar posição e vínculos, excluir/restaurar,
fechar/reabrir GPKG e projeto, selecionar ponto no mapa, testar cancelamentos e
encerramento. Conferir filtros de origem e atributos sem alterar a perspectiva.
Em redes: testar diâmetro com unidade conhecida, malha e ramificação, conjuntos
editáveis, reabertura e comparação; conferir CSV contra o WaterGEMS e criar conjunto
na cópia do modelo. Testes Qt não substituem essa aceitação visual/operacional.

Limites: sem critérios hidráulicos de simulação, sem escrita nativa de Selection
Sets, sem centralidade global, sem associação automática por proximidade. Busca de
candidatos e materialização de tabelas ainda têm etapas na GUI; o cálculo do grafo
é em worker. Desempenho em modelos maiores que o piloto requer ensaio dedicado.
