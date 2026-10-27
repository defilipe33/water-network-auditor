# Janelas e acompanhamento de operações — 1.4.0

## Transições previsíveis

A publicação da investigação integrada ocultava explicitamente auditoria GIS e
configuração WaterGEMS. Essa transição privilegiava o mapa, mas não explicava como
recuperar as telas. A configuração WaterGEMS também era filha do diálogo GIS; esconder
o proprietário podia esconder seus diálogos auxiliares e alterar o foco ao restaurá-los.

`janelas.Janelas` centraliza a identidade das interfaces, verifica objetos Qt destruídos
e oferece **Janelas / painéis** no menu do complemento, na auditoria, na configuração e
na investigação. As entradas aparecem conforme existam interfaces válidas:

- Mostrar auditoria GIS.
- Mostrar configuração WaterGEMS.
- Mostrar investigação integrada.
- Mostrar assistente, consulta, inspeção, inventário ou comparação disponíveis.
- Mostrar acompanhamento de operações.
- Restaurar janelas abertas.

A transição para a investigação continua intencional: as duas configurações ficam
em segundo plano e a barra do QGIS informa o caminho de recuperação. **Mostrar** não
reextrai modelos, não redefine formulários, não muda a seleção e não salva rascunhos.
Diálogos não modais gerenciados são irmãos sob a janela principal do QGIS; a relação
lógica com a aplicação permanece nos objetos Python, sem depender da árvore de widgets.
O inventário auxiliar é reutilizado no mesmo contexto, em vez de criar outra instância
a cada clique. Contextos diferentes continuam identificados separadamente.

Modais de escolha e confirmação continuam modais somente durante a ação. Uma tentativa
de recuperação não rouba foco do modal ativo. Assistente publicado não reaparece como
uma tarefa ainda pendente. Fechar antes da aprovação continua cancelando com segurança.
Ao minimizar/restaurar o QGIS, janelas ocultadas intencionalmente não são abertas por
um temporizador. A restauração explícita recupera as interfaces existentes.

Um painel de investigação fechado e desativado precisa reconstruir sua apresentação
a partir do pacote já carregado. Isso não executa nova auditoria ou extração hidráulica.
As guardas existentes resolvem mudanças de contexto, revisões e propostas pendentes.

## Acompanhamento compartilhado

`atividade.Atividades` mantém uma operação ativa, contexto, etapa, estado, detalhes e
um dock compacto, recuperável pelo menu. Ações rápidas não abrem outro diálogo: há
um atraso de 400 ms antes de mostrar o indicador. Processamentos conhecidos como longos
mostram o acompanhamento imediatamente. O usuário pode recolher o dock e recuperá-lo.

Estados distinguem andamento, cancelamento solicitado, cancelado, erro, etapa concluída,
espera de confirmação e operação concluída. Fechar um indicador não transforma uma
preparação em publicação aprovada. Uma etapa do assistente pode terminar sem que a
referência espacial esteja validada; isso é mostrado explicitamente.

Percentual só aparece quando há numerador e denominador verificáveis, como tubulações
analisadas. Ele representa a etapa indicada. Ao terminar essa etapa, as etapas seguintes
voltam a indeterminado. Sinais antigos baseados em marcos fixos são mostrados como
etapas, sem converter esses marcos em percentuais artificiais. **100% fica reservado
à conclusão da operação que efetivamente terminou**, após as validações pertinentes.

| Operação | Execução / feedback | Cancelamento |
|---|---|---|
| Auditoria GIS e reprocessamento | Núcleo original na GUI, com checkpoints limitados e contagem real de tubos | Cooperativo nos pontos existentes; restaura resultado anterior |
| Regenerar locais | Agrupador original, indicador indeterminado e confirmação separada da publicação | Cooperativo; não recalcula eventos |
| Reabrir GIS e recuperar camadas | SQLite/snapshot e construção da representação na GUI; atividade por etapa | Sem interrupção arbitrária de leitura/provedor |
| Extrair/atualizar WaterGEMS | Worker existente reutilizado; etapas de snapshot, cenário, grafo estrutural e hipótese aberta | Aguarda checkpoints, inclusive após cálculo indivisível |
| Persistir base topológica | GUI para camadas/provedores e validação; callbacks existentes | Cooperativo onde a persistência oferece ponto seguro |
| Assistente espacial e comparação de vértices | Worker e sinais existentes; captura GIS e mapa permanecem na GUI | Interrupção solicitada, sem terminar threads à força |
| Reabrir investigação persistida | Leitura SQLite/JSON e grafos em worker; widgets, camadas e mapa na GUI | Entre etapas; cancelado não publica a apresentação |
| Construir investigação integrada | Orquestração GUI com callbacks de cancelamento existentes e etapas explícitas | Nos pontos seguros da preparação/gravação |
| Comparar bases WaterGEMS | Worker para leitura e cálculo; resultado entregue por sinal na GUI | Entre leituras/cálculos; versões não são alteradas |
| Comparar investigações / publicação GIS | Acompanhamento na GUI, preservando diálogos e versionamento existentes | Conforme a confirmação e os pontos já disponíveis |
| Consultas paginadas | Atividade discreta se exceder o atraso; página limitada | Sem cancelamento fictício |
| XLSX, SHP, GPKG e acompanhamento | Acompanhamento indeterminado, com conclusão ou erro | Exportadores sem callback não oferecem botão que finja interromper |

## Responsividade e limites técnicos

O worker `Trabalho`, antes local ao assistente, foi reutilizado para leitura/comparação.
`Extracao` utiliza o mesmo contrato de sinais. Nenhum worker novo manipula widgets,
canvas ou providers de camadas pertencentes ao projeto. A reabertura em segundo plano
trata SQLite, JSON, grafo e valores geométricos próprios; publicação de camadas é GUI.

Não foram movidas rotinas inteiras com acesso a providers para threads apenas para
esconder o bloqueio. Persistem trechos síncronos, como decodificação de snapshots,
construção/publicação de camadas, algumas comparações e exportações. Há feedback,
mas chamadas indivisíveis podem atrasar a resposta da interface e do cancelamento.
A carga máxima de redes muito extensas e a segmentação adicional dessas etapas ainda
precisam de ensaio específico. Esta versão não declara responsividade contínua em
qualquer volume nem cancelamento imediato de qualquer operação.

`Operacao.ponto()` concentra o processamento de eventos dos checkpoints GUI, limita
a frequência a 80 ms e evita bombeamento recursivo. O filtro bloqueia comandos de entrada
nas interfaces vinculadas durante trabalho síncrono, preservando o cancelamento no
acompanhamento. Uma guarda adicional impede que a mesma ação acompanhada reentre por
temporizador durante esse bombeamento. Não há chamadas novas indiscriminadas a eventos
nos algoritmos hidráulicos ou geométricos.

Uma operação ativa ou um worker ainda executando impede encerrar/descarregar o
complemento. O contrato `allowExit()` da 1.3.1 permanece. Não há `terminate()` nem
publicação de um arquivo parcial como versão válida. Exportações que já produziam
arquivos individuais conservam seu contrato: em falha, conferir os arquivos gerados,
sem anunciar o conjunto como concluído ou alterar versões anteriores.

## Erros e recuperação

Falha encerra a atividade com estado próprio, restaura a disponibilidade do fluxo e
mantém detalhes técnicos consultáveis. Cancelamento não recebe estado de sucesso.
Os callbacks finais executam na GUI; threads encerradas são retiradas do controle.
O menu de janelas continua disponível e recuperar uma interface não descarta rascunhos.
O usuário pode repetir uma operação após resolver a causa sem reiniciar a auditoria.

## Aceitação no QGIS 3.44.15

1. Instale o ZIP em perfil de teste e reinicie. Abra auditoria e configuração WaterGEMS.
2. Confira que esconder a auditoria não esconde consultas/auxiliares de outro contexto.
3. Abra a investigação e leia a indicação de transição. Recupere cada interface pelo menu.
4. Digite um rascunho, alterne janelas e confira sua preservação, seleção e perspectiva.
5. Reabra o mesmo inventário/consulta e confira ausência de instâncias adicionais.
6. Abra o assistente; teste metadados, comparação, cancelamento, fechamento e publicação.
   Fechar uma etapa não pode declarar a referência validada nem produzir nova versão.
7. Observe atividade rápida, longa, percentual real e etapa indeterminada. Teste erro,
   repetição de comando e cancelamento. Confira que a base anterior permanece disponível.
8. Compare versões e abra investigação persistida; confirme que o mapa continua no
   thread principal e que a versão selecionada não é inferida pelo nome do arquivo.
9. Minimize/restaure o QGIS, alterne monitores e redimensione docks. Não deve haver
   reaparecimento involuntário de configurações escondidas nem perda de foco para modais.
10. Tente encerrar durante trabalho. Aguarde ou cancele em ponto seguro; depois salve
    rascunhos e encerre. Reabra bases e projeto; confira histórico, estilos e identidades.

Testes Qt offscreen, ensaios de processos reais e aceitação humana são registrados
separadamente. O teste de carga e a ergonomia em múltiplos monitores permanecem
pendências quando não exercitados no ambiente real do usuário.
