# Estabilidade, encerramento e finalização — 1.3.1

## Encerramento

QGIS 3.44.15 chama `QgsApplicationExitBlockerInterface.allowExit()`. O retorno
`True` autoriza a saída e `False` mantém o QGIS aberto. Na 1.3.0, os bloqueadores
implementavam `exitBlocked()`, que não pertence a esse contrato; o método abstrato
era chamado e impedia a saída normal.

O complemento registra um bloqueador geral, mesmo antes de abrir sua janela.
Sem aplicação aberta, ele autoriza imediatamente. Com aplicação aberta, delega a
`Aplicacao.preparar_saida()`: verifica processamentos e resolve rascunhos topológicos,
propostas, anotações e revisões/configuração GIS. A investigação aberta pelo controlador
não registra um segundo bloqueador. Uso independente pelo console conserva uma guarda
própria, com a mesma semântica. Guardas não chamam `quit()`, não terminam threads e
não autorizam recursivamente uma segunda tentativa enquanto um diálogo está aberto.

- Sem pendências: nenhuma confirmação adicional do complemento.
- Salvar: utiliza a persistência existente e somente libera se a gravação funcionar.
- Descartar: repõe os valores persistidos; não volta a perguntar sobre o mesmo rascunho.
- Cancelar: preserva o texto, a seleção, a perspectiva e o contexto da investigação.
- Processamento em andamento: adia a saída, informa na barra de mensagens e orienta
  aguardar ou cancelar pela ação existente. Não interrompe gravações de forma forçada.
- Erro ao verificar pendências: mantém o QGIS aberto e registra traceback no painel
  de mensagens **Water Network Auditor**, com orientação ao usuário.

Descarregar o complemento passa pela mesma verificação. Somente após autorização são
removidos bloqueador, ações e recursos próprios. O painel independente usa referência
fraca, verifica objetos Qt destruídos e cancela o registro ao fechar ou ser destruído.
Os hooks de fechamento continuam protegendo janelas abertas independentemente.

O QGIS pode exibir seu próprio aviso sobre camadas temporárias. Ele é distinto das
perguntas de rascunho do complemento. Essa proteção nativa não foi desabilitada.
Persistir resultados em GPKG continua indispensável; um projeto QGZ não é backup dos
conteúdos dos providers de memória.

## Navegação cotidiana

A janela principal agrupa seis ações: **Nova auditoria GIS**, **Continuar auditoria
GIS**, **Analisar com WaterGEMS**, **Continuar investigação integrada**, **Bases
WaterGEMS / atualizar** e **Comparar versões**. Cada ação informa seu propósito em
tooltip e reutiliza o fluxo existente de contexto, configuração e versionamento.

Os campos cadastrais opcionais das redes começam ocultos e podem ser exibidos sem
apagar seu mapeamento. A aba CRS prioriza o assistente; edição manual e consulta de
evidência anterior ficam em **Informações avançadas**. Identidades completas continuam
em tooltips e detalhamento; o cabeçalho prioriza nome, projeto e versão.

No painel, a lista e o diagnóstico têm alturas ajustáveis por divisor. Detalhes
técnicos começam recolhidos. **Anotar / decidir** leva diretamente ao campo rápido.
**Salvar observação e próxima ocorrência** preserva a classificação preliminar, quando
escolhida, e não exige responsável/documento. Outras edições mantêm a guarda existente.
**Próxima ocorrência** respeita cancelar e não altera perspectiva nem impõe zoom.

Conexão direta significa compartilhar nó cadastrado. Pertencer ao mesmo componente
significa existir um caminho no grafo, possivelmente através de outros elementos.
Nenhum dos dois resultados confirma operação real. A hipótese de válvulas abertas
respeita Active Topology e restrições de dispositivos; não é o estado do cenário.

Os três grupos de camadas e sua identidade por execução/origem continuam preservados.
Esta entrega não modifica os algoritmos, estilos originais ou dados persistidos para
melhorar a apresentação. A organização de janelas reutiliza área útil lógica Qt,
rolagem, divisores e memória opcional de tamanho; não altera o DPI global do Windows.

## Estado atual do produto

### Resultados registrados nesta entrega

- **630 testes automatizados aprovados** em 265,511 s: 600 anteriores preservados e
  30 novos. O teste antigo do bloqueador foi corrigido para verificar `allowExit()`
  com autorização positiva, em vez do método que não pertence à API.
- **14 processos reais do QGIS 3.44.15**, executando o ZIP instalado em perfil isolado
  Windows, terminaram com código zero e sinal `aboutToQuit`, sem timeout na matriz final.
  Casos: sem abrir a ferramenta, janela limpa, auditoria GIS, integrada, Salvar,
  Descartar, Cancelar seguido de nova saída, descarte espacial, thread concluída,
  thread cancelada cooperativamente, recarga, reabertura, painel independente e layout.
- Nas saídas limpas não houve pergunta de rascunho do complemento. Salvar e Descartar
  fizeram uma pergunta; Cancelar e a nova tentativa fizeram duas, uma em cada tentativa.
  Cancelar preservou texto/contexto. A reabertura recuperou anotações salvas e não
  encontrou a anotação descartada. Tentativas durante thread foram bloqueadas antes
  de uma saída posterior segura. A thread usa trabalho sintético controlado, não uma
  nova extração operacional completa.
- Diálogos nativos de temporárias/projeto foram respondidos apenas no projeto sintético.
  Na primeira versão do roteiro, esses avisos causaram timeouts: eles foram registrados
  como falhas do ensaio e não contabilizados como saídas limpas. Nenhuma preferência
  global de proteção foi desabilitada para executar o teste final.
- Ensaio pela API Qt, com escala de teste 150%, capturas examinadas e testes adicionais
  de áreas lógicas equivalentes a notebooks. Existe rolagem horizontal/vertical quando
  o conteúdo exige. Ergonomia na resolução/DPI e nos monitores do usuário permanece
  sujeita à aceitação humana, sobretudo a largura do dock e dos formulários extensos.
- Integridade ZIP, manifesto e correspondência com os fontes conferidos. Núcleos,
  agrupador, comparador, versões, persistência, decisões e roadmaps preservados por hash.

Não se declara aceitação humana interativa nem nova validação hidráulica operacional.
Os dados e perfis dos ensaios são sintéticos e não acompanham o repositório público.

As classificações abaixo distinguem implementação de aceitação operacional. Testes
sintéticos aprovados não substituem conferência de conectividade no WaterGEMS desktop.

| Funcionalidade | Estado | Evidência / pendência |
|---|---|---|
| Auditoria de fronteiras, classificações e agrupamento | Implementada e validada no escopo das regras aprovadas | Regressões sintéticas; piloto histórico e aceite informado pelo usuário. Novas entradas exigem conferência própria. |
| GPKG, SHP, XLSX e rastreabilidade | Implementada e validada nos ensaios registrados | Estrutura, reimportação e histórico; compatibilidade de novas versões externas continua sujeita a ensaio. |
| Reabrir, reagrupar, reprocessar e versionar auditorias GIS | Implementada e validada nos testes disponíveis | Manter backups e testar entradas reais sob parâmetros registrados. |
| Leitor, cenários/alternativas e grafo estrutural | Implementada, dependente de validação manual independente | Amostragem no WaterGEMS/Network Navigator ainda necessária; não representa simulação hidráulica. |
| Todas as válvulas abertas | Implementada, dependente de validação operacional | Hipótese separada, com Active Topology e restrições; não equivale à condição real. |
| Estados do cenário | Não implementada/liberada | Bloqueada até validar controles e condições operacionais. |
| Validação espacial assistida e evidências versionadas | Implementada, dependente de aceitação por modelo | Testes automatizados e uso real informado; reaproveitamento depende de assinaturas/contexto compatíveis. |
| Integração GIS × WaterGEMS, mapa e camadas | Implementada, dependente de validação manual ampliada | Ensaios sintéticos, versões persistidas e testes reais informados pelo usuário; fontes movidas exigem recuperação explícita. |
| Anotações, decisões e propostas | Implementada e validada em regressão/persistência | Confirmações e aprovações são ações humanas; registros não corrigem o modelo. |
| Comparação e validação posterior de intervenção | Parcialmente implementada para uso operacional amplo | Confronto e histórico implementados; critérios específicos por intervenção e modelos reais precisam de aceitação. Ausência não prova correção. |
| Encerramento e recarga do complemento | Implementada, sujeita aos resultados de ensaio desta versão | Conferir processos reais e roteiro abaixo; não aceitar timeout como sucesso. |
| Escalas DPI, notebooks e múltiplos monitores | Implementada, dependente de validação manual | Layouts lógicos e testes Qt; ergonomia e configurações reais devem ser conferidas. |
| Associação GIS espacial de válvulas/VRPs/boosters aos locais | Não implementada como próxima frente completa | Dispositivos do grafo já existem; associação espacial cadastral é outra funcionalidade. |
| Telemetria, planejamento de medição e suporte à calibração | Não implementada nesta entrega | Frentes futuras dos roadmaps; não confundir inventário com validação operacional. |
| Alteração automática do WaterGEMS | Fora do escopo atual | Não escrever no modelo nem fabricar elementos a partir de ocorrências. |

## Defeitos, limites e melhorias opcionais

O método abstrato de saída e a repetição de descarte são defeitos corrigidos nesta
entrega. CRS pendente, correspondência ambígua, fonte ausente e operação não mapeada
são limitações que exigem evidência ou recuperação; não se resolvem removendo bloqueios.
Uso diário prolongado, volumes muito grandes e múltiplos monitores são lacunas de
validação. Cores personalizadas, atalhos adicionais e rearranjos cosméticos são
melhorias opcionais e não bloqueiam a estabilização por si só.

## Plano de finalização da primeira versão estável

1. **Fechar estabilidade de sessão.** Executar o roteiro de saída, recarga e reabertura
   com pacote instalado e perfil isolado; depois realizar aceitação humana no ambiente
   habitual. Critério: nenhuma exceção abstrata, nenhuma perda, saída com código zero
   quando autorizada, cancelamento utilizável e nenhum timeout contado como sucesso.
2. **Aceitar o fluxo diário no piloto.** Trabalhar em cópia de resultados por vários
   dias: anotar, revisar, propor, exportar, salvar QGZ e reabrir. Confrontar registros,
   UUIDs, histórico, versões e hashes dos originais antes/depois. Critério: todas as
   observações recuperáveis e nenhuma herança indevida de confirmação.
3. **Conferir a interpretação do modelo.** Amostrar locais de continuidade, dispositivos
   sem jusante, componentes pequenos e divergências cadastrais no WaterGEMS e Network
   Navigator. Critério: registrar evidência para cada divergência e manter as não
   resolvidas explícitas; não anunciar conectividade operacional não validada.
4. **Verificar portabilidade e carga.** Repetir com outro município ou conjunto sintético
   representativo, nomes/campos/CRSs diferentes e volume definido com o usuário. Medir
   duração, memória, cancelamento e reabertura. Critério: ausência de nomes obrigatórios,
   sem congelamento irrecuperável e sem versões parciais publicadas.
5. **Publicar marco estável após aceite.** Congelar funcionalidades, executar toda a
   regressão, conferir ZIP instalado e segurança do histórico público. Documentar matriz
   de versões e limitações aceitas. Não retirar a indicação experimental apenas pela
   contagem de testes.

Associação de equipamentos, interpretação completa de controles, telemetria e novas
intervenções podem seguir em versões posteriores. Nenhuma delas foi implementada
automaticamente como parte desta revisão de estabilidade.

## Roteiro de aceitação humana no QGIS 3.44.15

Use cópias de resultados persistidos; não substitua modelos ou cadastros originais.

1. Instale o ZIP em perfil de teste e reinicie. Abra e feche o QGIS sem abrir a ferramenta.
2. Abra a ferramenta e feche sem edições. Não deve haver pergunta adicional do complemento.
3. Reabra auditoria GIS e depois investigação integrada; encerre sem rascunhos. Distinga
   eventual aviso nativo de camadas temporárias das perguntas do complemento.
4. Digite anotação e tente sair. Cancele: texto, caso, perspectiva e mapa permanecem
   utilizáveis. Tente novamente e salve. Reinicie e confira o histórico.
5. Repita com descartar. Confira que o texto não foi persistido e não há pergunta repetida.
6. Repita com conclusão, proposta e revisão espacial em rascunho, incluindo falha de
   gravação por destino indisponível. Falha não pode liberar saída com perda silenciosa.
7. Tente sair durante processamento. Aguarde ou solicite cancelamento cooperativo na
   janela correspondente. Saia depois de terminar; não encerre a thread à força.
8. Descarregue/recarregue o complemento com e sem rascunhos. Verifique que não há guardas
   residuais, diálogos duplicados, exceções de objeto Qt destruído ou perda de histórico.
9. Reabra o QGIS, as bases e o QGZ. Confira versões, estilos, visibilidade e ausência de
   cópias físicas adicionais de camadas. Referências legadas na árvore são preservadas.
10. Execute o fluxo selecionar → localizar → examinar → anotar → próxima. Confira zoom
    explícito, filtros, identificação do projeto e ausência de exigência documental simples.
11. Teste 1366 × 768 e 1920 × 1080 nas escalas Windows usadas, redimensionamento e troca
    de monitor. Confira botões acessíveis, rolagem e divisores; aceite visual é humano.

Registre por ensaio: versão do pacote, perfil, cenário, evidência, código de saída,
tempo, bloqueio intencional e timeout. Testes Qt automatizados e processos reais são
evidências complementares; não substituem a aceitação interativa humana.
