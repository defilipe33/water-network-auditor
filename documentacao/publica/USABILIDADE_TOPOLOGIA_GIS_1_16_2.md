# Navegação e revisão de conectividade GIS — 1.16.2

Na 1.16.1, localizar uma fonte exigia abrir **Opções do elemento**. Algumas listas abriam editores por duplo clique, enquanto outras exigiam um botão para chegar ao mapa. A ferramenta de captura também concorria com a troca de foco quando o QGIS desativava a ferramenta. A 1.16.2 adota gestos comuns nas vistas cartográficas e controla a finalização de cada captura.

## Navegar e trabalhar pelo mapa

No **Quadro do Modelo**, abra **Investigar minha rede → Analisar conectividade**. Use clique simples para consultar a linha, duplo clique para aproximar e destacar e botão direito para abrir as ações do registro sob o cursor. Nas tabelas com seleção múltipla, o menu de uma linha selecionada oferece **Enquadrar seleção**. A barra abaixo dos resultados indica a página e o total. O menu do cabeçalho permite escolher as colunas visíveis.

Os gestos também estão disponíveis no Modelo GIS, nas ocorrências de travessias, nos detalhes dessas ocorrências, nas diferenças entre hipóteses e nas principais consultas cartográficas do WaterGEMS. Ações indisponíveis mostram o requisito ao passar o mouse. Se faltar uma geometria confiável, o painel informa a limitação e conserva a identificação original.

## Definir fontes e conexões

1. Expanda **Definir fontes de água e conexões**. Adicione uma origem cadastrada, uma origem complementar no mapa ou uma conexão entre tubulações.
2. No editor, use **Selecionar tubulações no mapa**. O editor se oculta durante a captura. Cada clique acrescenta o ponto projetado sobre a tubulação. Quando houver alternativas, escolha a feição pela identificação e pela camada de origem.
3. Conclua com o botão direito ou cancele com Esc. O editor volta à posição anterior com os demais campos preenchidos. No cancelamento, voltam também os pontos que já estavam escolhidos. Se outra ferramenta for ativada no QGIS, a captura é cancelada e a ferramenta recém-escolhida permanece ativa.
4. Use **Buscar tubulação ou ajustar posição** para a alternativa por lista. Início e fim seguem a ordem dos vértices da geometria GIS. O sentido de escoamento fica fora desta investigação.

O duplo clique em uma fonte aproxima sua posição e realça as tubulações vinculadas disponíveis. Para incluir a extensão das tubulações no enquadramento, use **Enquadrar fonte e tubulações** no menu. As linhas tracejadas indicam associações entre a posição da fonte e os pontos de ligação declarados na rede.

## Revisar candidatas e reexecutar

Em **Conexões em T**, consulte a tubulação que termina, a receptora, a posição dos pontos, a distância e os componentes relacionados. Pelo menu da linha, registre **Confirmar conexão**, **Manter tubulações separadas** ou **Registrar como indeterminada**. O editor detalhado permanece disponível para revisão dos dados.

A tabela distingue interpretação, acompanhamento e participação. A confirmação cria uma revisão da conexão. Marque a relação na tabela ou escolha **Incluir na hipótese em edição** para participar do cálculo. **Reexecutar análise com estas alterações** oferece execução temporária, atualização da hipótese ou criação de outra. O comparativo informa uniões e divisões de componentes, além da extensão que ganhou ou perdeu acesso a uma origem.

## Excluir e recuperar complementos

**Excluir elemento complementar** mostra o elemento e as hipóteses salvas que o referenciam. A exclusão desativa o cadastro em uso por meio de uma nova revisão. As relações originais do GIS, as revisões fixadas e as análises publicadas permanecem preservadas. Ative **Mostrar complementos excluídos** para consultar ou recuperar o registro. Se desejar usá-lo de novo, inclua-o explicitamente na hipótese em edição.

A reexecução exata de uma hipótese histórica usa as revisões fixadas. Para salvar ou testar outra hipótese, retire complementos excluídos da seleção ou recupere-os. A 1.16.2 abre os cadastros e trabalhos da 1.16.0 e da 1.16.1. Se voltar à 1.16.1 após excluir um complemento na 1.16.2, a revisão excluída aparece como desativada.

## Implementação e limites

- `navegacao_cartografica.py` liga os gestos ao índice visível, preservando a linha correta após filtros, ordenação e paginação. O destaque utiliza geometrias persistidas ou correspondências verificáveis.
- A captura é finalizada uma vez por sessão. Os índices de seleção do editor são preparados na tarefa de leitura. O mapa trabalha com destaques temporários e mantém a simbologia das camadas de origem.
- A exclusão e a recuperação acrescentam registros ao cadastro complementar existente. As versões anteriores não sofrem migração destrutiva. Em complementos antigos, se a geometria da tubulação vinculada não estiver registrada na execução ou na revisão, o mapa apresenta as referências disponíveis.
- Geometria exibida, conexão aceita na hipótese e operação hidráulica representam coisas diferentes. A versão mantém o motor do grafo GIS da 1.16.1.
