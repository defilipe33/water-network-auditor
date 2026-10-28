# Restrições de percurso — 1.9.0

## Operação

Na investigação integrada, abra **Corredores / redes**, escolha origens e destinos
e expanda **RESTRIÇÕES DE PERCURSO**. São mostrados somente os tipos de dispositivos
presentes no modelo: PRV, TCV, FCV, PBV, retenções, bombas e outros tipos cadastrados.
Um booster só é tratado como equipamento quando existe um elemento topológico
correspondente; um polígono próximo não se transforma em bomba.

| Regra | Efeito |
|---|---|
| PERMITIR | Mantém a passagem que já existe na perspectiva |
| EVITAR | Prefere rotas com menos passagens pelo equipamento |
| BLOQUEAR | Remove a possibilidade de passagem no grafo de trabalho |

O fluxo é **selecionar terminais → definir restrições → calcular → comparar → salvar**.
Não há responsável, aprovação formal ou documento obrigatório.

### Preferência e critério de caminho

O padrão é **lexicográfico**: primeiro minimizar passagens por equipamentos marcados
EVITAR; entre rotas com a mesma contagem, minimizar o critério selecionado no módulo
(comprimento geométrico validado ou número de arestas). Uma rota mais longa pode ser
escolhida para evitar um equipamento. Se não houver alternativa, EVITAR admite usá-lo.
BLOQUEAR não admite esse uso.

Não se usa multiplicador arbitrário nem pontuação hidráulica. A alternativa
**Somente o critério de caminho** mantém os bloqueios, mas torna EVITAR informativo.
Passagens são contadas na entrada de um dispositivo com incidência única ou na
travessia entre suas portas, sem contar duas vezes entrada e passagem. Um dispositivo
usado como origem não é contado como uma entrada anterior ao início da rota.
As métricas de equipamentos distintos na união são separadas do custo por rota.

Comprimento geométrico não é perda de carga. Origens escolhidas não comprovam
disponibilidade de água, pressão nem sentido real de vazão. Alternativas continuam
sendo candidatas limitadas, sem garantia de enumerar todas as rotas possíveis.

## Exceções e estados

Expanda **Exceções individuais / hipóteses de estado**. Use busca por Label ou ID,
selecione linhas na tabela, aproveite equipamentos selecionados no QGIS ou clique
no mapa e confirme o candidato. Labels repetidos permanecem separados por ID e UID.
Escolha a regra e use **Aplicar aos equipamentos escolhidos**.

Para permitir somente algumas PRVs, por exemplo, bloqueie a categoria PRV e aplique
PERMITIR aos equipamentos escolhidos. Para bloquear uma única TCV, deixe a categoria
permitida e aplique BLOQUEAR àquela TCV. Remover uma exceção restaura a regra geral.
Uma exceção não cria aresta, não reativa elemento excluído da perspectiva e não
reverte direção obrigatória de uma retenção.

O estado manual é opcional: aberto, fechado, indisponível ou desconhecido. Fica
identificado como **HIPÓTESE DE INVESTIGAÇÃO**. A opção de bloquear fechados ou
indisponíveis usa essas hipóteses e, quando existentes, registros explicitamente
validados pelo leitor, com fonte, contexto e assinatura compatíveis. Um PERMITIR
individual não supera esse bloqueio de indisponibilidade.

O leitor atual não oferece interpretação validada de estados operacionais dinâmicos.
Códigos brutos, UDEs e Initial Settings não são convertidos automaticamente em estados
efetivos. Ausência de estado continua desconhecida. TODAS_VALVULAS_ABERTAS conserva
seu contrato; restrições manuais são hipóteses adicionais, não operação comprovada.
ESTADOS_DO_CENARIO permanece bloqueado.

Se uma origem ou destino estiver bloqueado, o cálculo explica o conflito. Escolha
outro terminal ou altere explicitamente a regra/hipótese e recalcule. A restrição
nunca é ignorada silenciosamente.

## Comparar e investigar interrupções

A tabela compara referência sem restrições adicionais e resultado restrito:
comprimento da união de tubos distintos, tubos, dispositivos, destinos alcançados e
inalcançáveis, componentes, equipamentos evitados/utilizados e tubos adicionados ou
removidos. Valores ausentes não viram zero. Detalhes das linhas conservam os IDs.

**Comparar e destacar diferenças no mapa** usa azul para trechos comuns, ciano para
adicionados e vermelho tracejado para removidos. São destaques temporários; estilos
originais e controle de aproximação permanecem preservados.

Quando uma rota deixa de existir, o diagnóstico separa alcance estrutural cadastrado,
perspectiva, restrições adicionais e limitações direcionais/disponibilidade. Barreiras
mostradas na rota de referência são evidências não exaustivas, não uma causa única.
Não existir caminho restrito não significa inexistir ligação no modelo original.
Uma rota alternativa não comprova viabilidade hidráulica.

Na linha inalcançável, **Criar local manual** permite escolher uma barreira candidata
ou o destino para investigar, quando há geometria e referência espacial validadas.
Não conecta elementos, não move equipamentos e não inventa ponto de ruptura.

## Perfis e conjuntos

Há predefinições sem restrições, evitar PRVs, sem bombas/boosters e evitar equipamentos
de controle, além de configurações personalizadas. **Salvar / renomear perfil** cria
revisão com identidade própria. Excluir retira o perfil da lista sem apagar seu
histórico ou alterar corredores já salvos.

Perfis usam a extensão existente `IGD_OBJETOS` / `IGD_OBJ_HIST`, com tipo
`PERFIL_RESTRICOES`, UUID, revisão anterior, versão topológica e perspectiva. Não há
um segundo banco de perfis ou migração destrutiva. Bases legadas continuam abertas;
a preparação original IGD mantém backup verificado quando necessário.

Importar/exportar perfil JSON permite uso explícito em outro contexto. Regras de
tipos ausentes são conservadas; exceções precisam de ID, tipo, UID e assinatura
compatíveis. Exceções de outro modelo e hipóteses de outro cenário exigem conferência
ou remoção. Não há associação automática por Label, nome do município ou proximidade.

Ao salvar um corredor, ficam registrados terminais, regras, exceções, estados e sua
origem, critério, perfil/revisão, contexto, equipamentos atravessados/evitados,
comparação e destinos não alcançados. Alterar parâmetros exige recalcular antes de
salvar. Inclusões manuais não podem contornar bloqueios.

Exportação completa reutiliza Pipes, Junctions e dispositivos realmente integrantes
do conjunto/rotas. `RESTRICOES_PERCURSO.json` acompanha a exportação com parâmetros,
comparação e identidade do conjunto. Queries e Selection Sets seguem o procedimento
de conferência já documentado; o SQLite original não é editado.

## Arquitetura e desempenho

`restricoes_percurso.py` valida regras e prepara uma cópia de trabalho. Bloqueios são
aplicados por visão filtrada de nós; nunca se unem os vizinhos de um dispositivo
retirado. O Dijkstra multi-origem existente recebe custos lexicográficos e conserva
arestas paralelas, predecessores, progresso, cancelamento e alternativas limitadas.
O cálculo de referência compartilha a estrutura de trabalho, evitando duas cópias
completas da rede. Não se calcula centralidade global.

No contrato histórico, ESTRUTURAL colapsa as incidências de retenções. Para o novo
cálculo restrito, a cópia de trabalho separa suas portas pela referência explícita
de jusante, usando o mesmo critério de incidência do resolvedor existente. Sem
orientação válida, incidências permanecem separadas e a pendência é informada.
Nenhum grafo persistido, componente histórico ou arquivo fonte é modificado.
A referência **sem restrições adicionais** também conserva essa direção obrigatória.
Conjuntos antigos continuam exportáveis sob seu contrato histórico.

## Roteiro de aceitação no QGIS 3.44.15

1. Instale o ZIP em perfil de teste; abra cópia de investigação e recupere um corredor.
2. Selecione Junctions por mapa/tabela, calcule sem restrições e confira o percurso.
3. Compare EVITAR e BLOQUEAR uma PRV em malha e em ramificação sem alternativa.
4. Bloqueie bombas e permita uma exceção; confira que a perspectiva não é ultrapassada.
5. Escolha uma TCV pela seleção QGIS e pelo mapa; teste Labels repetidos na tabela.
6. Registre estado manual fechado e desconhecido; confira a identificação de hipótese.
7. Teste retenção nos dois sentidos e orientação indeterminada, sem atalhos artificiais.
8. Salve/renomeie/exclua perfil, importe em contexto incompatível e confira os avisos.
9. Compare destaques e contagens, salve, reinicie o QGIS e reabra conjunto e perfil.
10. Exporte elementos, percursos e restrições; confira IDs e ausência de bloqueados.
11. Teste cancelamento, falha, rascunho não salvo, tela de notebook e encerramento.

Ensaios automatizados no processo QGIS e pela API Qt são distintos da aceitação humana.
Controles operacionais reais e Selection Set nativo no WaterGEMS continuam dependentes
de validação específica; não são simulados como fatos confirmados.

## Verificações da entrega

Em 28/10/2026: 1.082 testes aprovados de forma consolidada (1.027 anteriores e 55 de restrições). A suíte completa executou 1.081 testes; após o último refinamento de identificação do perfil, foram reexecutados os 55 testes do módulo e os 58 de corredores, sem somar duplicações. No pacote instalado do QGIS 3.44.15, ensaios por API Qt exercitaram seleção real de feição, clique confirmado, cálculo em worker, exceção individual, comparação, preservação de centro/escala, salvamento/exportação e reabertura em outro processo. A renomeação preservou a identidade e a revisão antiga continuou indicada como perfil histórico. Os processos finais encerraram com código zero e sem timeout. São ensaios automatizados, não aceitação humana completa.
