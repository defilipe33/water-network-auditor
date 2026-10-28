# Exportação completa, catálogo e relatório ilustrado — 1.8.0

## Exportar um corredor

Na investigação, abra **Corredores / redes**, recupere ou calcule o conjunto e salve
sua revisão. **Exportar para WaterGEMS** oferece lista CSV, percurso ordenado,
Queries por tipo, conferência auxiliar e instruções. Não altera o modelo hidráulico.

A lista contém elementos distintos: tubos escolhidos, extremidades do grafo e
os dispositivos efetivamente percorridos nas rotas mantidas. Não inclui elementos
por proximidade. Cada linha mantém ID, Label textual, tipo, UID, modelo, cenário,
perspectiva, versão, conjunto e motivo da inclusão.

PERCURSOS conserva rota, segmento, ordem, portas inicial/final, elemento, direção
da perspectiva e comprimento acumulado quando disponível. A direção não é vazão.
Remoções manuais dividem segmentos: a exportação não une os intervalos retirados.
Alternativas entram somente nos trechos explicitamente mantidos na seleção.
Conjuntos legados sem rotas recebem lista e aviso; nenhuma sequência é inventada.
A lista pode conter tubos acrescentados manualmente sem percurso ordenado.

### Queries e Selection Sets

A Bentley documenta [IN numérico](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0014274)
e [IN textual com aspas simples e distinção de maiúsculas](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0014334).
As consultas são separadas por tipo e divididas em lotes. Por padrão usam Label
único naquele tipo, preservando zeros e escapando aspas. Label vazio/repetido
bloqueia a consulta. ID só é oferecido após informar e confirmar o nome real do
campo no Query Builder; não se presume que o campo se chame DomainElementID.

O padrão de 100 valores/4.000 caracteres por lote é conservador e configurável;
não é um limite oficial comprovado do WaterGEMS. Valores nunca são truncados.
A interface permite copiar cada expressão. Confirme a sintaxe e os nomes dos
tipos na versão instalada, especialmente Labels contendo aspas especiais.

1. Abra o modelo e cenário identificados na exportação.
2. No Query Manager, crie consultas por tipo e lote; confira no Query Builder.
3. Execute as consultas, reunindo seleções por adição. Selection by Query não é
   importador CSV. Consulte os comandos de adição/seleção disponíveis na versão.
4. Confira por ID, tipo e Label; compare contagens por tipo e total.
5. Crie um Selection Set **estático** para preservar a fotografia. Seleções
   dinâmicas ligadas a consulta podem mudar quando o modelo mudar.
6. Exporte a seleção por FlexTable/CSV com cabeçalhos DomainElementID;Label;Tipo
   para **Conferir seleção CSV**. Confirme manualmente modelo e versão; o CSV
   sozinho não comprova sua origem. O relatório aponta ausentes, adicionais,
   duplicados e Labels divergentes.

Find Adjacent Nodes pode auxiliar, mas a adjacência não substitui a conferência
com os nós do percurso. Não inclui automaticamente válvulas/bombas vizinhas.
Referência: [seleções e FlexTables](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0057923).
Criação nativa/limites do Query Builder permanecem sujeitos a validação desktop;
nenhuma escrita direta em SQLite nem aprovação automática é realizada.

## Gerenciar investigações

O catálogo existente separa ativos, **Cópias de segurança / recuperação**, arquivados
e todos. Nome, UUID abreviado, projeto, tipo, versão, disponibilidade, classificação
e alteração ficam visíveis; modelo, cenário e outros filtros ficam recolhidos.

Identidade vem dos metadados. Hashes iguais agrupam cópias e preservam os caminhos
no detalhamento. Mesmo UUID com arquivos ativos divergentes gera conflito explícito.
O padrão de nome de backup técnico, corroborado pela identidade compartilhada,
separa backups esperados; arquivos isolados com esse padrão são candidatos a backup,
sem identidade reconstruída pelo nome. Nenhuma cópia divergente é escolhida sozinha.

Renomear modifica o **nome de exibição no catálogo**, sem mudar nome físico,
UUID ou análises. Arquivar mantém arquivo e histórico. Retirar oculta a referência
mesmo após reexame, sem apagar o GPKG. Adicionar novamente restaura a referência.
As preferências e ações ficam no mesmo catalogo_bases.sqlite, em gestao_bases e
histórico aditivo gestao_historico; o primeiro uso preserva backup verificado do índice.
O GPKG não recebe migração para essas operações.

A ação física avançada apresenta o arquivo e bloqueios. Investigações ativas,
camadas carregadas, transações SQLite pendentes, bases topológicas compartilhadas
ou dependências catalogadas impedem a operação. Após confirmação explícita, somente
o GPKG selecionado é movido por rename para RECUPERACAO na mesma unidade, com
manifesto e hash. Não move fontes GIS, outros backups ou modelos. Recuperar arquivo
movido usa o manifesto, verifica hash e recusa sobrescrever o caminho original.
Referências fora do catálogo não podem ser descobertas universalmente: confira o
plano antes de mover. Não mova arquivos usados por outra aplicação.

## Relatório de investigação

Na aba Configurações e fontes, **Gerar relatório de investigação** abre uma janela
recuperável pelo gerenciamento de janelas. Usa somente registros persistidos:
rascunhos não salvos não aparecem. Selecione todas, analisadas, pendentes, correção
necessária, manuais, ocorrência selecionada ou filtros ativos de todas as páginas.
Não reprocessa a auditoria. PDF, XLSX e snapshot JSON usam a mesma seleção.

O PDF inclui capa, contexto/versionamento, resumo da seleção, índice paginado,
diagnóstico, resultado, motivo, observações, elementos, regiões, localização e
histórico opcional. Textos longos fluem para páginas adicionais. Interpretações
não são confirmações hidráulicas. Não exige responsável, ART, assinatura ou documento.

Mapas são renderizados por QgsMapRendererParallelJob, sem captura da interface,
com camadas próprias e clones das fontes cartográficas. Mantêm norte da grade,
barra métrica, legenda e CRS, sem alterar estilos/seleções de entrada. O padrão de
extensão mínima evita zoom excessivo; margem, contexto e enquadramento atual do
canvas podem ser escolhidos. Elementos distantes geram aviso e mapa complementar.
Não há edição interativa da posição de rótulos nesta versão.

Prévia produz capa, resumo e uma ocorrência em PDF e mostra o mapa na janela.
A prévia é claramente uma amostra, não o resumo de toda a seleção. A geração final
usa pasta nova e área temporária; PDF é reaberto antes da publicação. Cancelamento
ou falha preserva relatórios anteriores. XLSX usa o exportador tabular já validado;
texto que excede 32.767 caracteres em uma célula é recusado sem truncamento.

Requisitos do relatório no Python QGIS: ReportLab, Pillow e pypdf, além de openpyxl
para XLSX. Não são instalados automaticamente. Estão disponíveis no ambiente de
validação; em outras instalações, ausência gera mensagem de erro sem publicar
parciais. Preferências de aparência são locais no QSettings por investigação;
autenticação/URLs de geocodificação não são salvas nessas preferências.

## Referências cartográficas e privacidade

Pode usar camadas do projeto: raster local, GeoPackage vetorial, MBTiles via GDAL
ou conexões XYZ/WMS/WMTS pelo provedor QGIS apropriado. **Conexões cadastradas**
abre o gerenciador nativo do QGIS; adicione a camada desejada e atualize a lista.
Não é necessário recadastrar a autenticação. Outra fonte aceita URI QGIS, sem
persisti-la no relatório. Prefira authcfg do QGIS a senhas/tokens na URI.

Sem mapa-base é o padrão. Para usar uma fonte, informe os créditos e confirme que
sua licença permite a exportação/armazenamento desejados. A composição permite
opacidade, cinza, brilho e contraste, respeitando as possibilidades do provedor.
Os estilos de ruas ou satélite dependem das camadas escolhidas; o complemento não
fornece um provedor universal gratuito nem remove créditos/logotipos.

Mapas online exigem autorização específica: o provedor recebe a área/escala do
mapa. Para múltiplas ocorrências exige também permissão de exportação em lote.
Não há scraping, pré-carregamento de cidades, download de tiles em massa ou cache
paralelo. O provedor QGIS/Qt usa seu cache HTTP configurado; fontes locais são
preferidas para relatórios grandes. Timeout/erro gera mapa sem base e aviso claro.
Nome/provedor/CRS/licença/atribuição/data são registrados; URI, authcfg e credenciais
não são serializados no snapshot cartográfico.

A localização prioriza atributo cadastral explicitamente escolhido, depois ruas
locais e referência manual. Campo NOME não é presumido como endereço. Logradouros
são indexados espacialmente, reprojetados explicitamente e medidos em CRS métrico.
Eixo mais próximo não é endereço exato; interseção 2D não comprova cruzamento em
nível (por exemplo, viadutos). Ausência/ambiguidade permanece indicada.

**PERMITIR CONSULTAS EXTERNAS DE LOCALIZAÇÃO** vem desligado. Mesmo habilitado,
a consulta é unitária, por botão, somente para a ocorrência selecionada. Envia
latitude/longitude e formato, nunca IDs, Labels, atributos ou topologia. Configure
serviço HTTPS corporativo/contratado compatível com reverse JSON e informe termos,
atribuição, custos e armazenamento conhecidos. Authcfg permanece no QGIS.
Há intervalo, timeout, bloqueio de redirecionamento e cache de sessão somente
quando autorizado pelo provedor. O relatório não dispara geocodificação em lote.

A [política Nominatim pública](https://operations.osmfoundation.org/policies/nominatim/)
impõe limites e restrições a serviços genéricos e dados confidenciais. Essa instância
não é oferecida como endpoint integrado. Use fontes locais/serviços autorizados;
automação não transfere essa responsabilidade ao serviço público.

## Limitações e aceitação

Dados cartográficos externos refletem a data da captura, não uma reprodução
histórica garantida. PNGs podem ser preservados apenas conforme licença. JSON
registra a seleção, versões, revisões e contexto usados. Locais manuais entram sem
exigir evento automático. Nenhum modelo hidráulico é atualizado pelo relatório.

Roteiro: abrir investigação antiga; verificar ativos/backups e renomeação; arquivar,
restaurar e retirar sem perda; conferir o plano de recuperação física em cópia;
exportar corredor com dispositivo, conferir Queries/seleção no WaterGEMS; gerar
PDF offline com anotação e manual; adicionar base local e ruas, comparar detalhe/
contexto, testar filtros, texto longo, cancelamento e reabertura. Testar fontes
corporativas autorizadas, falha de rede, atribuições e DPI de notebook. Distinguir
API Qt automatizada de aceitação humana. Não declarar Selection Set nativo criado
nem serviços externos homologados sem sua conferência no ambiente de uso.
