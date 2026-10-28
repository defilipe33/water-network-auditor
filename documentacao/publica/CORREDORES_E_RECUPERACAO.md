# Corredores alimentadores e recuperação de análises — 1.7.0

## Operação

Abra a investigação integrada e use **Corredores / redes…**. O padrão é
**Corredores alimentadores**. Escolha origens e destinos, calcule, examine as rotas
e os destaques, revise a seleção e salve um conjunto nomeado. Não é necessário
responsável, aprovação ou documento. Nada é escrito no modelo WaterGEMS.

Os métodos são distintos:

| Método | O que representa |
|---|---|
| Caminho entre pontos | Uma rota escolhida entre uma origem e um destino |
| Corredores alimentadores | União das rotas escolhidas para os destinos selecionados |
| Seleção cadastral | Tubos que atendem aos filtros de atributos |
| Pontes topológicas | Tubos cuja remoção separa conectividade fraca, incluindo ramificações |
| Critério combinado | E/OU entre cadastro e corredores; pode alterar a continuidade |
| Conectividade crítica | Cortes topológicos por pontes; não criticidade hidráulica |

As pontes deixaram de ser incluídas automaticamente em corredores. Sem terminais,
os métodos de caminhos não executam e orientam a seleção. Conjuntos antigos da
1.6.0 permanecem consultáveis com identificação de legado; não são renomeados
silenciosamente como corredores alimentadores.

## Escolher terminais

Expanda Origens e Destinos. Junctions são permitidas, assim como reservatórios,
tanques e dispositivos compatíveis com o grafo. **Origem é o ponto inicial escolhido,
não comprovação de fonte de água, pressão ou sentido de vazão.**

- Busca por Label ou DomainElementID mostra candidatos em tabela; selecione as
  linhas e use Adicionar linhas escolhidas. Labels repetidos não são resolvidos
  arbitrariamente. A pesquisa tabular mostra até 200 candidatos por consulta.
- Usar seleção QGIS reconhece elementos da versão WaterGEMS por metadados e UID,
  sem depender do nome da camada. Seleções GIS sem correspondência técnica não
  são convertidas silenciosamente em nós WaterGEMS.
- Clicar no mapa usa raio métrico e referência espacial validada. Confirme o
  candidato; proximidade não comprova conexão. Esc cancela e restaura a ferramenta.
- Destinos dos polígonos selecionados usa interseção geométrica no CRS adequado,
  conservando fonte, atributos e assinatura dos polígonos. Não significa região
  hidráulica comprovada. Mais de 500 terminais por adição exigem refinar a seleção,
  sem amostragem silenciosa. Dispositivos com várias portas exigem escolha explícita.

Portas distintas de bombas/retenções não são fundidas pelo DomainElementID.
Terminais ausentes ou indisponíveis são identificados. ESTRUTURAL e
TODAS_VALVULAS_ABERTAS conservam os contratos existentes de atividade e dispositivos.
ESTADOS_DO_CENARIO continua bloqueado.

## Critérios e métricas

Menor número de arestas conta os enlaces e passagens de dispositivos do grafo.
Menor comprimento soma as geometrias de tubos em metros, somente com referência
espacial validada. Passagens de dispositivos não acrescentam comprimento.
Comprimentos ausentes não viram zero. Comprimento geométrico não é perda de carga.

Para várias origens, cada destino recebe a rota de menor custo desde uma das
origens disponíveis. Empates usam ordem reproduzível, sem afirmar unicidade ou
preferência hidráulica. Não é árvore geradora mínima nem otimização hidráulica.
O usuário pode comparar conjuntos calculados com origens/critérios diferentes.

O cálculo principal usa Dijkstra multi-origem com um predecessor identificado por
aresta, preservando tubos paralelos e memória linear. Reconstrói caminhos somente
para os destinos escolhidos. A análise usa o grafo completo da perspectiva; filtros
cadastrais não recortam esse universo silenciosamente.

Alternativas são **candidatas não exaustivas**: até oito exclusões temporárias de
arestas distribuídas pela rota principal, com novas buscas dirigidas. Não modifica
o grafo persistido. São apresentadas até três candidatas por destino, ordenadas
por custo, sem garantia de serem as K menores rotas globais. A comparação de
alternativas fica limitada a 50 destinos por cálculo para controlar o custo.
Não encontrar alternativa nessa busca não prova sua inexistência.

Por tubo, consultar rotas principais, destinos distintos, classe no conjunto,
comprimento, diâmetro bruto/unidade e dispositivos associados. **Rotas e destinos
não são vazão ou demanda.** Dois ou mais destinos nas rotas escolhidas marcam um
corredor compartilhado; um único destino indica ramo associado. Essa participação
depende dos terminais escolhidos e não mede importância global do grafo. Unidades
de diâmetro sem evidência continuam NÃO CONFIRMADAS; a unidade das coordenadas não
valida todas as propriedades físicas.

A tabela de rotas compara custo, comprimento, tubos e dispositivos. A tabela de
elementos tem rolagem horizontal. É possível acrescentar explicitamente tubos de
uma alternativa à seleção final, além da edição manual existente.

## Continuidade e mapa

São registrados destinos alcançados/inalcançáveis e componentes fracos das rotas.
Na gravação, registra-se também a continuidade da seleção efetiva após combinações
e edição manual: remover um conector pode separar o conjunto. Múltiplas origens
em sistemas separados não exigem um componente único.

Destinos sem caminho não recebem ligação fictícia. Avisos do componente de destino
são pistas para investigação, não prova da causa do bloqueio. Um botão permite
criar local manual na geometria validada de um destino inalcançável; não presume
que ali esteja a ruptura e não altera a topologia.

Nos destaques: verde para origem, vermelho para destino, azul para trechos
compartilhados, laranja para ramos/rota, magenta tracejado para alternativas,
ponto magenta para dispositivos e cinza para destino inalcançável. O zoom continua
explícito. A representação própria de conjuntos possui classe e contagens; os
estilos das fontes e das auditorias originais não são alterados.

## Recuperar anotações e resultados

O resumo INVESTIGAÇÃO CARREGADA informa dados efetivamente lidos: locais
automáticos/manuais, registros de análise, observações, conjuntos e quantidade
de análises na perspectiva atual. Nome, UUID da investigação, versão topológica,
perspectiva e filtros ficam disponíveis no contexto/tooltip.

Na abertura, a perspectiva padrão ainda é ESTRUTURAL e a fila mostra pendências.
Resultados de manutenção/adequação na perspectiva de válvulas abertas podem estar
preservados e ocultos por essas duas condições. Isso não demonstra perda de dados
nem falha de atualização.

**Mostrar todas as análises salvas** consulta esta investigação em todas as
perspectivas, independentemente de filtros e paginação. Inclui resultados atuais,
históricos, anotações e revisões legadas sem convertê-los em novas conclusões.
Observações completas são legíveis em células/tooltips. Abrir ocorrência nesta
perspectiva resolve rascunhos, muda a perspectiva explicitamente, limpa os filtros
que a ocultavam, mostra Todos e navega à página do UUID correto.

Um registro de contexto antigo sem ocorrência atual continua visível em consulta
somente leitura; não é associado por nome, proximidade ou outro ID. O histórico
selecionado permanece visível na consulta; abrir a ocorrência mostra seu contexto
atual, sem reativar uma conclusão antiga. Atalhos dão acesso a casos, análises,
anotações, manuais e conjuntos. A consulta não migra nem escreve na base.

## Persistência e exportação

Reutiliza IGD_OBJETOS, IGD_OBJ_HIST e IGD_OBJ_VINCULOS; não cria sistema paralelo.
Rotas, terminais/portas, perspectiva, critério, métricas, limites e edição manual
acompanham o conjunto na versão correspondente. Revisões anteriores não são apagadas.
Parâmetros alterados exigem recálculo; falha/cancelamento não autoriza salvar a
seleção antiga como se representasse os novos parâmetros.

GPKG conserva histórico e relações. CSV de seleção mantém DomainElementID, Label
textual, tipo, modelo, cenário, versão, perspectiva e UUID, acrescidos das métricas.
O acompanhamento XLSX/CSV inclui ROTAS_CORREDORES, METRICAS_CORREDORES e
DESTINOS_INALCANCAVEIS; dados técnicos extensos continuam divididos sem truncamento.

O CSV não é importação nativa comprovada de Selection Set. A Bentley documenta
[seleções/consultas e FlexTables](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0057923)
e [criação de Selection Sets](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015896).
Na versão instalada, conferir a lista por ID/tipo/Label no modelo correspondente,
aplicar consulta ou seleção, conferir contagem e criar o conjunto por ação explícita.
A criação nativa continua pendente de validação operacional; nunca se escreve no
SQLite original para inserir Selection Sets.

## Aceitação manual

No complemento instalado: reabrir uma base 1.6.0, conferir o resumo, localizar
análises de outra perspectiva e registros fora da fila. Criar caminho entre duas
Junctions por busca, seleção e clique; comparar arestas/comprimento e alternativas.
Adicionar destinos, conferir tronco compartilhado, ramos e um destino desconectado.
Salvar, reabrir, editar e exportar sem mudar fontes/versões anteriores. Testar
cancelamento, DPI de notebook e fechamento do QGIS. Ensaios Qt não equivalem à
aceitação humana. Modelos maiores que o piloto ainda exigem teste de carga dedicado.
