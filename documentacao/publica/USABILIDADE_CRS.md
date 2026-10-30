# Inspeção tabular, telas e referência espacial

## Inspeção

O painel de diagnósticos preserva o resumo e as evidências expansíveis e acrescenta
**Elementos e vínculos**. Cada linha apresenta tipo, ID GIS, camada GIS, Label
WaterGEMS, DomainElementID, componentes, vínculo, diagnóstico e revisão. Candidatos
múltiplos permanecem individualizados. Identificadores brutos e chaves técnicas podem
ser mostrados pelo menu **Colunas**; não são substituídos pelos valores de apresentação.

Na inspeção geométrica há abas de tubulações e eventos, além dos detalhes completos.
O inventário de componentes também oferece membros em colunas. Os elementos de uma
proposta aparecem em tabela própria. Os vínculos continuam sendo resolvidos pelas
identidades técnicas, nunca pela posição dos textos nas tabelas.

As tabelas de consulta permitem busca, ordenação, deslocamento e redimensionamento
das colunas e rolagem horizontal. O menu **Colunas** controla a visibilidade. Valores
longos não são truncados nos dados: o texto integral está no tooltip e no diálogo
aberto por duplo clique. `〈nulo〉`, `〈vazio〉` e `0` são apresentações distintas.

## Janelas e DPI

Um adaptador comum atende janela principal, seleção de bases e versões, integração,
configuração WaterGEMS, inspeção, diagnósticos, decisões, propostas e exportação.
Utiliza a área útil do monitor e coordenadas lógicas Qt, sem multiplicar novamente
o DPI. Formulários podem quebrar linhas; conteúdos extensos têm rolagem; ações finais
permanecem fora da rolagem principal. Grupos de botões se reorganizam em uma ou duas
colunas. Docks inseridos no QGIS continuam redimensionáveis.

**Lembrar tamanho e posição nesta tela** é opcional. A geometria restaurada é limitada
à tela disponível, inclusive se o monitor anterior não existir mais. Não são alteradas
as configurações globais de escala do Windows.

## Configurar WaterGEMS

1. Abra uma auditoria geométrica concluída e clique em **ANALISAR COM WATERGEMS**.
2. Na aba **Modelo e cenário**, abra uma base existente ou selecione o SQLite salvo,
   cenário e perspectiva e crie uma base topológica. Essa consulta não exige CRS.
3. Na aba **Correspondência GIS × Label**, selecione explicitamente a coluna de cada
   camada GIS que contém o identificador usado como Label da tubulação WaterGEMS.
   O campo da auditoria geométrica é mostrado separadamente e pode ser diferente.
4. Use **Prévia** para consultar contagens por camada e amostras dos dois ambientes.
   Há contagens de correspondências únicas, registros repetidos, nulos, vazios,
   não encontrados e inconsistências geométricas. Uma chave cadastral única, sem
   comparação espacial, é identificada como tal; não constitui vínculo inequívoco.
5. Na aba **CRS e unidades**, verifique a referência espacial antes de integrar.

Label é um atributo de apresentação do WaterGEMS; não é automaticamente DomainElementID,
ID GIS ou chave técnica. Textos com zeros à esquerda são preservados. Uma repetição
em qualquer origem selecionada impede tratar o vínculo como inequívoco.

## CRS e unidade: campos diferentes

| Campo | Significado |
|---|---|
| CRS | Referência espacial projetada, com unidade metro, usada na comparação GIS |
| Unidade bruta | Unidade das coordenadas armazenadas no WaterGEMS |
| Fator bruto → metro | Multiplicador das coordenadas brutas antes da comparação |
| Evidência | Documento ou conferência independente que sustenta CRS e unidade |
| Método | Como a confirmação foi obtida |
| Operador histórico | Campo opcional preservado de bases antigas; não exigido no novo assistente |
| Estado | VALIDADO, PENDENTE ou INCOMPATIVEL, com motivo |

Copiar o CRS de processamento GIS é uma ação explícita e **não confirma** a referência
do WaterGEMS. A escolha da unidade atualiza o fator correspondente; outros fatores
podem ser declarados. Não há CRS ou fator selecionado pelo nome do município.

### Reutilizar evidência

**Verificar evidência existente** consulta outra base ou JSON. A reutilização exige
equivalência da identidade e composição técnica do modelo: cenário, alternativas,
elementos, geometrias e valores resolvidos. Caminho ou nome igual não bastam.
O registro conserva assinatura de contexto, hash e fonte da evidência, método,
data e registro anterior. Operador é opcional. Cancelar mantém o formulário anterior.

Um JSON antigo sem assinatura reproduzível fornece somente valores candidatos;
exige nova validação. Bases antigas com declaração de CRS/fator/fonte continuam
legíveis e são identificadas como **declaração legada**, sem inventar metadados.

### Nova validação

Examine a prévia e suas coordenadas e geometrias, disponíveis pelo menu **Colunas**.
As coordenadas apresentadas nessa etapa são candidatas, calculadas com os valores
informados. A prova reaproveita o comparador de todos os vértices já existente.
São exigidos pares inequívocos suficientes (pelo menos três, ou todos em modelos
com menos de três tubulações) e referência de CRS identificada; nome e aprovação formal não são necessários.
O ajuste geométrico sozinho não comprova datum, unidade ou conectividade hidráulica.

Após confirmar, **Criar base / salvar validação em nova versão** grava um arquivo novo,
com UUID próprio e referência à versão anterior. Não reextrai o modelo, não altera o
grafo e não sobrescreve a base anterior. A validação em memória ainda não salva é
indicada como pendente de gravação.

## Integração e bloqueios

Antes de processar, um resumo mostra auditoria, modelo, versão, cenário, perspectiva,
campos GIS, CRS, fator e fonte. Sem referência validada, a ferramenta oferece consultar
somente a topologia, ir à validação ou cancelar. Nenhuma integração espacial é
publicada nessa condição. A camada espacial e o SHP real continuam sujeitos à
validação. ESTADOS_DO_CENARIO permanece indisponível.

## Verificação manual no QGIS desktop

1. Instale o ZIP atualizado em perfil de teste e reinicie para evitar módulos antigos.
2. Em 1366 × 768 e 1920 × 1080, com escalas de 100%, 125%, 150%, 175% e 200%, abra
   principal, versões, catálogo, WaterGEMS, integração, inspeção, decisões e propostas.
   Confirme acesso por rolagem aos campos e acesso aos botões finais.
3. Redimensione, mova entre monitores, memorize geometria e reabra em outra tela.
4. Busque, ordene, oculte e reexiba colunas. Confira texto longo, nulo, vazio e zero.
5. Abra uma base sem referência: consulte a topologia; tente integrar e cancele.
   Confirme que a auditoria e as revisões anteriores permanecem utilizáveis.
6. Escolha campos GIS distintos do campo da auditoria. Confira exemplos, repetições,
   não encontrados e inconsistências; não aprove vínculos ambíguos.
7. Teste evidência compatível, incompatível e JSON sem assinatura. Cancele o reuso
   e confira a preservação dos valores. Faça confirmação documental quando cabível.
8. Salve em nova versão, feche e reabra. Confira proveniência e preservação da base
   anterior. Gere integração apenas depois da validação e examine o resumo.

Os testes automatizados de áreas lógicas e APIs Qt não substituem essa conferência
interativa, a leitura visual de todos os campos e o comportamento físico dos monitores.


Fluxo refinado na 1.12.1: [quatro etapas, opções avançadas e capturas antes/depois](REFINAMENTO_ESPACIAL_1_12_1.md).
