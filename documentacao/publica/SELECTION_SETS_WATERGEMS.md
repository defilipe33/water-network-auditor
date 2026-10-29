# Selection Sets WaterGEMS — 1.11.0

## Fluxo de uso

Abra uma investigação integrada associada à base topológica da versão que deseja representar. No painel, escolha **IMPORTAR SELECTION SETS DO WATERGEMS…** → **Selecionar modelo / atualizar** → marque pastas ou conjuntos → **Importar conjuntos marcados** → **Mostrar camadas no QGIS**.

O modelo é aberto somente para consulta. A importação e os históricos são gravados na investigação integrada; camadas cartográficas são novos GeoPackages em pasta escolhida. Não há escrita no WaterGEMS ou no cadastro GIS original.

A árvore permite pesquisa por nome/caminho, seleção múltipla e seleção de pasta com descendentes. Apresenta nome original, caminho por ancestrais, tipo, quantidade declarada, compatibilidade, ID e totais por tipo. Nomes repetidos e Labels repetidos são preservados, sem serem utilizados como identidade.

A operação exige uma investigação e base topológica associadas; não cria uma nova base topológica somente por selecionar um SQLite.

## Referência técnica e esquema

Consultado o [Model Builder Composer](https://github.com/defilipe33/model-builder-composer/tree/b3205a2579eee782375b757f7a0b96f40f7a88ff), commit `b3205a2579eee782375b757f7a0b96f40f7a88ff`, especialmente `repository/selection_sets.py`, `database/connection.py`, `database/schema.py`, `repository/model_repository.py`, `gui/selection_set_dialog.py`, README_V311 e README_V32.

O Composer documenta `HMISelectionSet.SelectionSetElementIDs` como sequência little-endian uint32, com quantidade conferida por `SelectionSetCount`. Resolve o nome prioritariamente por `HMIModelingElement.ElementID = SelectionSetID`, campo Label. Classifica membros pelas tabelas raiz e situação de exclusão. Seu leitor consultado lista pastas junto aos conjuntos e não reconstrói ParentID. Não foi encontrada nele uma matriz comprovada de compatibilidade por versão comercial do WaterGEMS.

A leitura reutiliza `bases.snapshot` (SQLite backup API) para uma fotografia consistente, incluindo WAL comprometido. Não inclui alterações ainda não salvas no WaterGEMS. O adaptador WNA utiliza `Banco`, já existente, com URI SQLite `mode=ro` e `query_only`. Não incorpora módulos inteiros nem adiciona dependência do Composer. A referência externa permanece fora do ZIP e do Git público deste projeto.

No esquema HMI examinado foram observados:

| Campo / relação | Uso |
|---|---|
| HMISelectionSet.SelectionSetID | Identidade do conjunto ou pasta no modelo |
| HMIModelingElement.ElementID / Label | Nome original |
| HMISelectionSet.ParentID | Pai por identidade; zero representa raiz no formato examinado |
| HMISelectionSet.SelectionSetElementType | Marcador observado: 1 pasta, 0 conjunto |
| HMISelectionSet.SelectionSetType | Tipo bruto; 1 com lista explícita foi observado nos estáticos |
| SelectionSetCount / SelectionSetElementIDs | Contagem declarada e sequência uint32 |
| IsDeleted | Exclusão cadastral, independente de Active Topology |
| HMIDomainDataSet.Guid / DomainDataSetID | Identidade do modelo pelo leitor existente |
| HMISchemaVersionInfo | Metadados de formato, quando presentes |

Esses valores são um contrato do formato observado, não uma enumeração universal de todas as versões Bentley. Marcadores inconsistentes, ciclos e pais ausentes são sinalizados. Não se inventam pastas pelos nomes. O caminho é representado também como lista de IDs, sem depender do texto contendo separadores. Ordem original dos itens não foi identificada; a apresentação usa ordem determinística por identidade/profundidade.

A Bentley documenta [pastas de Selection Sets a partir do WaterGEMS/WaterCAD 2024](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0036262). Isso confirma o recurso do produto, mas não documenta o contrato binário interno do SQLite. O suporte desta entrega é baseado no esquema local examinado e nos testes, não em garantia para qualquer versão.

## Membros, Queries e correspondência

As sequências brutas, inclusive IDs repetidos, são preservadas. Os membros distintos são usados nos vínculos e no mapa para evitar duplicar uma feição dentro do mesmo conjunto. Uma feição pode pertencer a vários conjuntos.

A identidade do modelo, UID/tipo e assinatura de geometria/topologia/exclusão são comparados com a base topológica aberta. Referências ausentes, excluídas ou incompatíveis permanecem nos metadados e não recebem geometrias por aproximação. O cenário e alternativas utilizados são registrados. Uma atualização do SQLite pode exigir atualizar também a base topológica para representar membros alterados.

Tipos dinâmicos ou desconhecidos permanecem **COMPOSIÇÃO NÃO VERIFICADA**. Definição e BLOB original são conservados, mas não se executa uma expressão arbitrária nem se utiliza cache como composição atual comprovada. A Bentley alerta que [conjuntos baseados em Query podem refletir uma avaliação anterior](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0058810).

Quando necessário, execute e confira a seleção no WaterGEMS e exporte uma lista com **DomainElementID, Tipo e Modelo**; Label é opcional e textual. A importação CSV exige identidade de modelo compatível. Não reconstrói pastas nem Query original e fica identificada como alternativa. Não há, nesta entrega, importação automática genérica de SHP sem mapeamento de identidade; o arquivo não é associado apenas por proximidade ou Label.

## Persistência e atualização

Reutiliza **IGD_OBJETOS, IGD_OBJ_HIST e IGD_OBJ_VINCULOS**, com tipos `SELECTION_SET_WG` e `IMPORTACAO_SELECTION_WG`. Não cria outro sistema de revisões. O snapshot de importação preserva pastas, relações, nomes, definições e assinaturas; cada conjunto importado conserva seus membros e pendências.

A identidade contextual é derivada de investigação + modelo + SelectionSetID. UUID da revisão e referência à anterior são automáticos. A extensão existente faz backup verificado; a importação é preparada em cópia temporária, validada e publicada em uma transação com conferência de escritores concorrentes. Cancelamento não publica importação parcial. Reimportação idêntica dos mesmos conjuntos não duplica o histórico.

Atualize pelo mesmo comando de leitura, selecione os conjuntos e importe. São registradas inclusões/remoções de membros, conjuntos ou pastas, renomeações e mudanças de pai por ID. Desmarcar um conjunto não o exclui. Remoção comprovada na fonte gera exclusão lógica do conjunto importado, preservando histórico. Listas CSV alternativas não removem automaticamente conjuntos nativos.

**Comparar com outra investigação** recupera as importações persistidas em dois GPKGs, confere identidade de modelo e salva evidências nas tabelas de comparação existentes. Não transfere análises, prioridades ou RESOLVIDO. Diferenças de cenário/alternativas ficam explicitadas. Modelos sem identidade correspondente não são reconciliados por nome.

## Cartografia e organização local

O grupo **SELECTION SETS WATERGEMS** utiliza subgrupo contextual por versão e identidade, com pastas aninhadas por IDs. Pastas vazias são preservadas no snapshot e podem aparecer na árvore sem criar camadas vazias. Hierarquia não recuperável permanece indicada; pode ser organizada manualmente no QGIS.

Linhas, pontos e outras geometrias válidas são separados em camadas persistentes. A base topológica precisa ter CRS/unidades validados para representações espaciais. Membros sem geometria confiável não recebem uma posição fictícia. Manifesto e metadados conservam os casos omitidos/pendentes.

Cores iniciais distinguem conjuntos. Espessura, transparência, rótulos e visibilidade são configuráveis pelas propriedades normais do QGIS. Salve o projeto `.qgz` para conservar preferências, estilos e organização local. A reabertura reutiliza as camadas identificadas e não restaura compulsoriamente a posição de uma camada movida pelo usuário. A organização original continua nos metadados, independente da árvore local.

A criação de camadas usa o thread principal para provedores QGIS, com acompanhamento e pontos seguros entre lotes; leitura SQLite, importação e comparação usam workers existentes. Em operações de provedor indivisíveis, o cancelamento aguarda o ponto seguro. Não há encerramento forçado de threads.

GeoPackage conserva atributos completos. A cópia SHP é opcional: campos técnicos têm até 10 caracteres, e o manifesto JSON/GPKG preserva nomes, tipos, nulos e textos além dos limites DBF. Não se declara um SHP equivalente à base relacional inteira.

Uma envolvente **convex hull** só é criada por solicitação. É identificada como **APROXIMADA / NÃO OFICIAL**, com método registrado, contorno tracejado e preenchimento transparente. Não equivale a limite cadastral de setor ou zona de VRP.

## Investigação, comparação e relatórios

O filtro de conjuntos/pastas usa **pelo menos um membro por identidade WG** e combina por E com os filtros já ativos. Não cria diagnósticos nem recalcula/recorta o grafo dos corredores. **Limpar filtros** remove esse escopo. Destaques são temporários e o zoom é explícito.

É possível comparar os conjuntos/pastas marcados com o item destacado da árvore: comuns, exclusivos e tipos, sem classificar sobreposição como erro. Exportar metadados conserva as listas completas. Comparações entre versões incluem mudanças de nome/pasta/membros e podem ser incluídas no relatório.

O relatório offline utiliza o gerador PDF/XLSX existente, com caminhos hierárquicos nos títulos e membros identificados. A opção de relatório com mapa-base reutiliza a configuração e as permissões já existentes: prévia, enquadramento, fontes locais e serviços externos autorizados. Nenhuma consulta externa é necessária por padrão. Um conjunto cadastral não é apresentado como um problema hidráulico confirmado.

## Aceitação manual

1. Instale o ZIP em perfil de teste no QGIS 3.44.15 e abra cópia de uma investigação.
2. Leia o SQLite correspondente; confira nomes, pastas, conjuntos vazios e aninhados no WaterGEMS.
3. Importe parte dos conjuntos; confira membros ausentes, excluídos, repetidos e incompatíveis.
4. Gere camadas persistentes; configure cores, rótulos, visibilidade e organização local.
5. Salve e reabra `.qgz`; reabra a investigação sem o SQLite original disponível e recupere as camadas.
6. Selecione uma pasta e filtre ocorrências; limpe o escopo e confirme que o grafo não mudou.
7. Atualize uma cópia do modelo, importe na base correspondente e compare nomes/pais/membros.
8. Gere relatório offline e confira a prévia com fonte cartográfica permitida.
9. Teste cancelamento, ausência de CRS validado e fonte movida, preservando os resultados anteriores.

Ensaios automatizados PyQGIS e API Qt no QGIS instalado são registrados separadamente da **aceitação visual humana**, que permanece pendente. Composição dinâmica, cobertura de outras versões WaterGEMS e operação hidráulica não são consideradas comprovadas.
