# Relatórios, Queries e acompanhamento — 1.8.1

## Encerrar o acompanhamento de uma ocorrência

Em **Resultado da análise**, use **✓ Marcar como resolvido** ou **Resolvido e
próxima**. A observação de acompanhamento é opcional; não há exigência de
responsável, justificativa, documento ou proposta. Campos de análise já editados
são salvos antes da mudança de situação. Rascunhos de outros formulários continuam
protegidos por Salvar/Descartar/Cancelar.

**RESOLVIDO** significa que o caso não precisa de acompanhamento adicional no
momento. Não comprova correção hidráulica, não cria intervenção e não altera o
WaterGEMS. Diagnóstico, prioridades e resultado técnico permanecem separados.
Uma separação intencional pode ter resultado **MANTER CONFIGURAÇÃO ATUAL** e
acompanhamento **RESOLVIDO**.

A fila inicial **Em aberto** exclui somente resolvidas. Combine-a com os demais
filtros. Use **Resolvidas** ou **Todas as ocorrências** para consultar o histórico,
selecionar o caso e **Reabrir investigação**. **Pendentes**, **Em análise**,
**Necessitam investigação adicional** e **Reavaliação necessária** são recortes
adicionais. Salvar um resultado técnico, isoladamente, não resolve o acompanhamento.
Resolver e avançar conserva os filtros e a perspectiva e não aproxima o mapa.

### Persistência e novas versões

Os registros ficam no mesmo GeoPackage integrado. A extensão aditiva
`IGD_ACOMPANHAMENTO` guarda UUID, investigação/ocorrência/perspectiva, situação
anterior e nova, observação, data UTC, versão WaterGEMS, assinatura técnica e
referência ao registro anterior. `IGD_ACOMP_SCHEMA` identifica a migração e seu
backup. Histórico imutável, chaves estrangeiras, transação e verificação da última
revisão impedem sobrescrita silenciosa por outra sessão. Abrir bases antigas não
as migra; a primeira gravação prepara o esquema com backup completo verificado.

**Comparar versões** também compara os acompanhamentos. A equivalência considera
identidades técnicas, cenário, perspectiva, elementos envolvidos, ligações locais
e evidências. UUID novo da execução ou mudança de nome/caminho não basta para
invalidar uma resolução. Alterações relevantes exigem reavaliação; correspondência
ambígua não transfere a resolução. Aplicar a comparação é explícito e não substitui
trabalho já registrado na nova investigação. Não há transferência automática entre
arquivos apenas por proximidade ou nome. O histórico da origem permanece intacto.

## Gerar relatório sem configuração de serviços

Abra **Gerar relatório de investigação**, escolha ocorrências e destino. PDF é o
formato principal; XLSX é opcional. **Incluir mapas** utiliza camadas da investigação.
O padrão funciona sem internet e sem cadastrar provedor ou licença:

- **Automático:** utiliza somente mapa-base local com permissão reconhecida. Na
  ausência de fonte adequada, gera os elementos da investigação sem mapa-base.
- **Sem mapa-base:** renderiza rede, dispositivos e limites locais.
- **Selecionar:** escolhe uma fonte específica e verifica suas condições.

Uma fonte carregada no QGIS pode continuar sendo um serviço externo. Disponibilidade
não comprova licença. Fontes remotas exigem permissão real, créditos, autorização
para enviar a área e, em vários mapas, permissão para lote. Restrições explícitas
não são liberadas por uma caixa de seleção. As opções técnicas ficam recolhidas.

Antes de qualquer consulta não autorizada, a interface oferece gerar sem mapa-base,
escolher outra fonte, configurar serviço autorizado, uma ocorrência quando permitida,
ou cancelar. Se a fonte falhar durante a renderização, pode-se continuar sem ela ou
cancelar. O relatório registra a ausência; tubulações e limites são preservados.
Não se publicam arquivos parciais como relatório concluído.

**Prévia de uma ocorrência** renderiza somente um caso. Use o enquadramento atual
do mapa, nas opções avançadas, para ajustar sua extensão. A prévia não desloca o
canvas. Para o relatório completo, há filtro independente: incluir, excluir ou
somente resolvidas. Resumo e detalhes distinguem acompanhamento e resultado técnico.

### Localização

A busca automática prioriza campos cadastrais de localização, logradouros locais,
resposta de serviço previamente autorizado e descrição manual. Campos genéricos
como `NOME` não são presumidos como endereço. Uma camada local de ruas com campo
textual inequívoco pode ser reconhecida; com ambiguidades, escolha camada e campo
nas opções avançadas. Não se faz geocodificação externa automática. Sem evidência,
o texto é **Localização não identificada**, preservando contexto e coordenadas no
detalhamento técnico.

## Queries identificáveis

Em **Exportar para WaterGEMS**, a prévia apresenta tipo, lote, quantidade, campo,
validação sintática e origem. Cada consulta contém um tipo apenas. Exemplos
sintéticos: `PIPE_LOTE_001_100_ELEMENTOS.txt` e `PRV_LOTE_001_1_ELEMENTO.txt`.
Nomes são seguros para Windows; o tipo original permanece no manifesto.

`INDICE_QUERIES.csv` acompanha os arquivos, com ordem, tipo, nome, lote,
quantidade e total por tipo, campo, situação sintática, modelo e versão.
`MANIFESTO_QUERIES.json` registra identidades e hashes. Labels permanecem textuais,
inclusive zeros iniciais; listas extensas são divididas sem truncamento. A prévia
permite copiar a expressão selecionada.

O guia incluído orienta criar Query do tipo correto, colar, executar e conferir cada
lote antes de acrescentá-lo a um Selection Set estático. Uma nova Query pode
substituir a seleção anterior. CSV não é anunciado como importador nativo. A sintaxe
documentada e a exportação não comprovam criação de Selection Set no WaterGEMS
desktop; essa conferência continua necessária na versão instalada.

## Aceitação interativa

1. Instale o ZIP 1.8.1 em perfil de teste no QGIS 3.44.15 e abra cópia de investigação.
2. Confira **Em aberto**, marque um caso sem campos obrigatórios e avance. Verifique
   diagnóstico/prioridades/resultados inalterados, filtros e zoom preservados.
3. Em **Resolvidas**, reabra o caso. Resolva novamente, reinicie o QGIS e confira o
   histórico e a recuperação. Teste Cancelar com observação ainda não salva.
4. Compare uma versão equivalente e uma com alteração de ligação local. Confira a
   reavaliação conservadora antes de aplicar a comparação.
5. Gere PDF e XLSX offline, com todas, sem resolvidas e somente resolvidas. Confira
   contagens, resultado técnico e acompanhamento em colunas distintas.
6. Abra a prévia, ajuste o enquadramento, escolha ruas locais e um mapa-base local
   permitido. Teste em tela de notebook e escala DPI habitual.
7. Para serviço externo autorizado, confira os termos antes de permitir requisições.
   Teste cancelamento e recuperação sem base em falha de rede/autenticação.
8. Exporte Queries, compare nomes/índice/manifesta e quantidades por tipo. No
   WaterGEMS, confira sintaxe, cada seleção e a união estática final.

Testes Qt/PyQGIS e automação de processo QGIS são registrados separadamente da
aceitação humana. Serviços online reais, licenças particulares e Selection Sets
nativos não são considerados validados apenas por testes simulados.

## Verificações da entrega

Em 28/10/2026: **1.027 testes automatizados aprovados**, incluindo os 947 anteriores e 80 novos. Uma regressão antiga passou a selecionar explicitamente a fila Pendentes, pois Em aberto agora é independente do resultado técnico. Nenhum teste foi removido. O ZIP foi instalado em perfil temporário do QGIS 3.44.15: resolver/reabrir/avançar, filtros, perspectiva, zoom, relatórios offline, mapa-base local, rua sintética, Queries, persistência em outro processo e encerramento limpo foram exercitados pela API Qt. A prévia foi conferida visualmente e preserva sua altura com rolagem. Esses ensaios não substituem a aceitação humana do roteiro acima.
