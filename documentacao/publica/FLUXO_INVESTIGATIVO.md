# Investigação prática e árvore de camadas — 1.3.0

Resultados e limites dos ensaios: [validação da entrega](VALIDACAO_FLUXO_1_3.md).

O fluxo principal é abrir a auditoria, analisar com WaterGEMS, investigar no mapa e
registrar observações. Propostas e confirmações continuam sendo ações explícitas.
Nenhuma ação escreve no modelo WaterGEMS ou no cadastro GIS original.

## Conclusão da validação espacial

Após gravar a nova versão, o assistente verifica integridade e relacionamentos,
confere a referência validada, ativa a base na janela principal e recupera CRS,
unidade, fator, evidência, responsável, tolerância e mapeamento das colunas GIS.
O catálogo é atualizado pelo mecanismo existente e a relação de origem é preservada.
Ao terminar a thread, o assistente fecha automaticamente e devolve o foco à configuração.

O responsável (*) é exigido somente para essa confirmação definitiva e validado antes
de escolher o destino/gravar. Campos ausentes são destacados, mantendo os valores já
informados. Fechar antes da gravação cancela com segurança; durante o trabalho solicita
interrupção no próximo ponto seguro. Fechar pelo X após publicar mantém a base ativada.
Cliques repetidos não iniciam nova gravação enquanto houver trabalho/publicação.
Se a ativação falhar após a gravação, a interface informa o arquivo para recuperação
e bloqueia nova publicação pelo mesmo assistente.

## Três formas de registrar investigação

| Ação | Exigência | Significado |
|---|---|---|
| Salvar anotação | Texto não vazio | Observação, sem conclusão automática |
| Salvar conclusão preliminar | Classificação preliminar e texto | Hipótese ou necessidade de conferência |
| Salvar decisão confirmada | Conclusão explícita, justificativa, responsável, fonte e evidência suficiente | Interpretação técnica fundamentada |

A aba **ANÁLISE E DECISÃO** começa com andamento, anotação rápida e classificação
preliminar opcional. **Salvar somente andamento administrativo** mantém a conclusão
anterior. VERIFICADO não significa que a topologia foi corrigida.

Os campos de confirmação ficam na seção recolhível **CONFIRMAÇÃO TÉCNICA / EVIDÊNCIAS
AVANÇADAS**, com requisitos explicados previamente. HIPOTESE e INDEFINIDO não comprovam
conclusão definitiva. A interface destaca pendências e permite preparar explicitamente
a mesma interpretação como hipótese preliminar, sem converter registros anteriores.
Nessa ação, a observação é obrigatória e os detalhes tentativos são copiados para o
texto da preliminar. Após salvá-la, o formulário de confirmação volta ao estado
anterior, sem perder os detalhes registrados nem exigir aprovação da hipótese.

O operador padrão é opcional e configurado explicitamente nessa seção. Anotações usam
esse operador; não herdam automaticamente o responsável de uma conclusão anterior.
Sem operador, continuam válidas e ficam sem responsável informado.

Cada anotação/preliminar recebe UUID próprio, data UTC, execução, ocorrência,
perspectiva e assinatura do contexto. Pode haver várias observações para o mesmo caso.
São registros anexados em `IGD_REGISTROS`, relacionados a `IGD_OCORRENCIAS`, com triggers
contra alteração/exclusão. As revisões confirmadas e propostas anteriores ficam intactas.
A primeira extensão tem backup completo verificado. A leitura de bases antigas não as migra.
Salvar, descartar e cancelar continuam protegendo rascunhos nas mudanças de contexto.

O histórico mostra os registros e a exportação de acompanhamento acrescenta a aba
`ANOTACOES_PRELIMINARES`. O GPKG conserva a estrutura relacional completa. A exportação
não converte observações ou propostas em intervenções aprovadas.

## Ambiente principal e mapa

O painel integrado informa projeto, execução GIS, execução WaterGEMS, cenário e
perspectiva. Resumos distinguem casos sem registro, com análise/anotação, preliminares,
confirmados e propostas. São contagens por contexto; podem se sobrepor e não representam
erros hidráulicos comprovados. Filtros incluem andamento e casos com registros.

A priorização existente continua baseada em evidências. Componentes isolados e
ligações entre setores permanecem situações investigáveis, não erros automáticos.
Os filtros começam recolhidos quando um caso já está selecionado e podem ser reabertos.
O dock tem largura inicial proporcional e continua redimensionável; depois da primeira
abertura, o ajuste manual da largura não é refeito a cada troca de caso.

Destaques são efêmeros: tubos azuis, nós verdes, dispositivos magenta, limites ocres
e candidatos em laranja tracejado. Polígonos têm preenchimento transparente e bordas
mais finas abaixo dos elementos. Os estilos das camadas originais não são alterados.

Selecionar não impõe zoom. **Aproximar mapa** mantém margem mínima de contexto de
50 m em cada lado; **Ajustar extensão dos elementos** considera os elementos envolvidos.
Há comandos para componente, seleção GIS e remoção dos destaques. Falta de geometria
ou CRS válido é reportada, sem aproximação espacial inventada.

## Árvore do QGIS

Grupos próprios na raiz:

- **AUDITORIA GIS**: subgrupos por execução e origem.
- **TOPOLOGIA WATERGEMS**: representações independentes carregadas pela consulta de base.
- **INVESTIGAÇÃO INTEGRADA**: eventos/locais, perspectivas e representações associadas.

Somente grupos com metadados da ferramenta são reutilizados. Nome igual não autoriza
adotar grupos do usuário. Os subgrupos exibem projeto/nome, versão e UUID abreviado;
`[ATIVA]` indica o contexto ativo. Fontes, UUIDs e nomes técnicos ficam em propriedades
das camadas/grupos. A posição na árvore e o nome amigável não determinam a identidade.

As camadas WaterGEMS possuem nomes amigáveis. As demais mantêm os nomes existentes
quando usados pelos consumidores anteriores. Auxiliares ficam em seções recolhidas;
as escolhas de visibilidade das camadas reutilizadas são mantidas. Seleções e renderers
não são trocados pela organização. Camadas cadastrais não são movidas ou apagadas.

Reabrir a mesma fonte/execução reutiliza as camadas. Municípios, fontes e versões
distintos ficam separados. Fonte divergente ou camada inválida gera aviso de recuperação,
sem substituição silenciosa. Nós legados ou organizados manualmente são preservados;
podem existir referências visuais ao mesmo resultado em um grupo antigo e no grupo novo,
sem novas cópias dos dados. Grupos legados vazios podem ser removidos manualmente.

Ao reabrir `.qgz`, providers de memória podem voltar vazios. Reabra a investigação ou
carregue novamente a base pela ferramenta: ela restaura somente caches próprios vazios,
com identidade, esquema e quantidade compatíveis, a partir da versão persistente.
Não recalcula eventos, não troca o layer ID, não muda o renderer nem sobrescreve caches
não vazios. O projeto sozinho não substitui os GeoPackages; mantenha-os disponíveis.

## Temporárias

A conferência espacial fica em **VALIDAÇÃO ESPACIAL — TEMPORÁRIA**, no contexto de
origem. Não são elementos hidráulicos nem resultados persistentes aprovados.
Na janela principal há opção explícita para remover somente temporárias da ferramenta
ao encerrar. O padrão é conservá-las; nenhum arquivo em disco é apagado.

## Roteiro manual no QGIS 3.44.15

1. Atualize pelo ZIP e reinicie o QGIS. Abra a auditoria/base e valide a referência.
   Confira responsável ausente, preservação do formulário, clique repetido e fechamento
   automático com todos os campos de integração atualizados.
2. Gere/reabra a investigação. Redimensione o dock, consulte filtros e escolha um caso.
3. Salve uma anotação sem fonte/responsável. Registre uma preliminar sem comprovação.
   Tente confirmar com HIPOTESE/INDEFINIDO e confira destaque dos campos, sem perda do texto.
4. Configure opcionalmente operador padrão. Confirme que observações não recebem o
   responsável de uma decisão antiga por herança implícita.
5. Consulte histórico, propostas e exportação. Cancele uma troca de caso com rascunho.
6. Confira rede sob limites transparentes, zoom explícito, extensão dos elementos e limpeza.
7. Carregue outra versão/projeto e reabra a anterior. Confira grupos, UUIDs, visibilidade,
   seleções, estilos e ausência de novas cópias de camadas.
8. Salve `.qgz`, feche e reabra o QGIS. Reabra a investigação e confira a restauração
   das representações e dos registros. Teste fonte movida/inválida sem apagar versões antigas.
9. Teste limpeza opcional das temporárias e confirme que cadastro e saídas persistentes ficam intactos.

Ensaios automatizados e pela API Qt não equivalem a aceitação humana por cliques ou
conferência operacional. Modelos/dados reais não acompanham a distribuição pública.
