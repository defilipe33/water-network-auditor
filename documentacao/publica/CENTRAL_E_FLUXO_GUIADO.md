# Central de Trabalho, preparação e contextos — 1.12.0

Esta entrega reorganiza a navegação sobre os processadores existentes. Não muda
o núcleo geométrico, agrupador, leitor WaterGEMS, resolvedor, comparador espacial,
regras de dispositivos ou significado das decisões.

## Como começar

1. Abra o complemento e crie um projeto de trabalho ou escolha um projeto recente.
   Projetos têm UUID próprio; nomes iguais não fundem seus resultados.
2. Em **Preparação guiada**, prepare GIS e WaterGEMS na ordem conveniente.
   **Utilizar existente** recupera resultados sem reprocessar.
3. Consulte o estado dos requisitos na Central. Abrir uma janela não conclui uma
   etapa; arquivo existente não equivale a base validada.
4. Para integrar, confira a referência espacial e as correspondências exigidas
   pelo fluxo existente. **Retomar operação desejada** retorna à ação interrompida
   depois de resolver suas pendências, sem publicar automaticamente.
5. Para continuar outro dia, use **Retomar última base do projeto** ou o catálogo.
   Arquivos movidos devem ser relocalizados por UUID no catálogo existente.

**Guiado / Avançado** muda a apresentação, conservando os mesmos formulários,
dados e algoritmos. Os atalhos antigos continuam disponíveis em uma seção
recolhível da auditoria GIS e em **Janelas / painéis**.

## Ferramentas e dependências

| Tarefa | Requisitos reais |
|---|---|
| Nova auditoria GIS | Entradas e parâmetros conferidos pelo formulário GIS |
| Preparar WaterGEMS | Modelo salvo ou base persistida; não exige GIS |
| Consultar conectividade | Base topológica íntegra; não exige CRS validado |
| Corredores / ilhas sem GIS | Base topológica e terminais/origens; cálculo no grafo persistido |
| Validar referência / correspondências | Bases GIS e WaterGEMS disponíveis |
| Criar investigação integrada | GIS concluído, topologia compatível, referência e correspondências válidas |
| Selection Sets / relatório | Investigação integrada conforme o contrato atual |
| Recuperar / consultar histórico | Catálogo e arquivo selecionado conferido ao abrir |

Os estados incluem CONCLUÍDO, PENDENTE, EM ANDAMENTO, REQUER VALIDAÇÃO,
INCOMPATÍVEL, INDISPONÍVEL e OPCIONAL. Nem toda ferramenta usa todos os estados.
Durante atividades, a Central encaminha ao acompanhamento compartilhado.

A consulta independente usa um adaptador transitório explicitamente identificado
como **CONTEXTO_TOPOLOGICO_SEM_GIS**. Não cria auditoria GIS fictícia, investigação
ou decisões persistidas. Resultados podem ser exportados explicitamente como
evidência JSON; para o fluxo completo de conjuntos e decisões, use a investigação.
Mapas e comprimentos permanecem condicionados à referência/unidade válida.

## Painel integrado ou janela independente

O seletor de apresentação alterna o mesmo QDockWidget e seu conteúdo. Não cria
outra sessão ou outra cópia de rascunhos. Há suporte a redimensionamento,
maximização, minimização e recuperação por **Janelas / painéis**.

Preferências ficam em `preferencias_interface.ini` na pasta de trabalho: modo,
geometria, área de acoplamento, tela, seção e nível de navegação. Coordenadas Qt
são lógicas; não se aplica o fator DPI novamente. Se a tela anterior não estiver
disponível, o retângulo é limitado à área útil de uma tela atual. Não se restaura
o estado global do QGIS nem se reorganizam camadas originais.

## Contexto WaterGEMS e cenários

**Explorar cenários e setores** apresenta cenário, pai e cadeia efetiva de Active
Topology. **O cenário base não é a união dos filhos.** Cada cenário exige uma
extração própria ou uma base correspondente, identificada por modelo e cenário.
Havendo várias versões, a escolha é explícita.

A troca confere a candidata antes de resolver rascunhos. Salvar, Descartar ou
Cancelar seguem as guardas existentes; cancelar conserva o contexto. Uma
investigação de outra versão deixa de ser a investigação ativa, permanece no
catálogo e pode ser reaberta. Decisões e RESOLVIDO não são transferidos.

Associações opcionais entre cenário e região/Selection Set usam IDs e versão
explícitos, com histórico no índice do projeto. Não são inferidas por nomes nem
comprovam cobertura hidráulica. Exigem alvos disponíveis em uma investigação do
mesmo modelo. Comparação avançada entre cenários permanece fora desta entrega.

## Selection Sets, relatórios e dois monitores

Em **Cenários e conjuntos → Explorar Selection Sets**, abra uma investigação,
selecione o modelo correspondente e importe os conjuntos desejados pelo leitor
existente. A pasta original usa identidades recuperadas, sem reconstrução por
nomes. Publique suas camadas para visualização; grupos e simbologia seguem o
mecanismo anterior. Consulte o [guia de Selection Sets](SELECTION_SETS_WATERGEMS.md).

Em **Apresentar e recuperar → Gerar relatório**, escolha ocorrências e destino.
O funcionamento padrão é offline, com mapas das fontes locais. Fontes online
continuam condicionadas às permissões aplicáveis. Veja
[relatórios e Queries](RELATORIOS_QUERIES_ACOMPANHAMENTO.md).

Para trabalhar em outra tela, selecione **Janela independente**, mova a janela
pelo título e redimensione ou maximize. Volte a **Painel integrado** para acoplar.
Se uma tela for desconectada, use **Janelas / painéis** para recuperar a interface;
o enquadramento considera as telas presentes. Este procedimento está implementado,
mas o ensaio físico com dois monitores permanece pendente.

## Arquitetura e persistência

- `dependencias.py`: contratos e recomendações sem executar processamentos.
- `contexto_trabalho.py`: projetos por UUID, referências e histórico de associações;
  consulta somente leitura de metadados/integridade dos resultados existentes.
- `central.py` / `preparacao_guiada.py`: navegação e encaminhamento aos formulários.
- `apresentacao.py`: apresentação do mesmo conteúdo, preferências e enquadramento.
- `cenarios_ui.py`: seleção explícita do contexto, sem união ou reinterpretação.
- `topologia_direta.py`: adaptação de interface aos núcleos de corredores e ilhas.
- `controlador.py` / `watergems_ui.py`: orquestração e guardas existentes.

`projetos_wna.json` é um índice de navegação na pasta de trabalho, não substitui
os metadados, históricos e UUIDs dos GeoPackages. A gravação usa temporário e
substituição atômica, sem apagar um índice anterior diante de erro. Arquivos de
navegação são locais e ignorados pelo Git. Os esquemas analíticos não são migrados
por esta entrega. Reabra o GPKG original para acessar revisões antigas.

## Validação e aceitação

Veja [capturas e registro dos ensaios](VALIDACAO_INTERFACE_GUIADA.md).
Capturas são reais de widgets do QGIS instalado, usando somente dados sintéticos.
Teste por API Qt e revisão visual interna são distintos de aceitação humana.

Roteiro de aceitação:

1. Instalar o novo ZIP e reiniciar o QGIS 3.44.15.
2. Abrir a Central sem bases; tentar integrar e conferir a explicação e o retorno.
3. Criar projeto e recuperar GIS/WG existentes em qualquer ordem; conferir UUIDs.
4. Testar conectividade sem GIS e sem CRS; confirmar bloqueio apenas espacial.
5. Preparar correspondências e validar CRS pelo assistente existente; retomar.
6. Abrir investigação, editar anotação, alternar apresentação e cancelar troca de
   projeto/cenário; conferir rascunho, filtros, seleção e zoom preservados.
7. Trocar entre cenário pai e filho de modelos de teste. Conferir Active Topology,
   versão, ausência de transferência de decisões e acesso à investigação anterior.
8. Associar explicitamente região ou Selection Set; reabrir e conferir histórico.
9. Maximizar, minimizar, restaurar e acoplar; reiniciar e recuperar a última base.
10. Conferir tela pequena, DPI e monitor desconectado em equipamento apropriado.
11. Encerrar sem pendências e com Salvar/Descartar/Cancelar; confirmar saída real.

Permanecem pendentes a aceitação do usuário com seus projetos operacionais e os
ensaios físicos em duas telas e resoluções não disponíveis no equipamento de teste.
