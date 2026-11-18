# Aparência clara e escura — 1.14.1

A correção mantém o Quadro do Modelo, o cadastro multifonte e a navegação da 1.14.0. O Auditor utiliza a paleta efetiva da janela principal do QGIS. Não é necessário escolher outro tema dentro do complemento.

## Diagnóstico

A 1.14.0 impunha fundo claro, texto azul escuro e botões brancos no novo ambiente. As áreas internas herdavam o fundo escuro do QGIS. Essa combinação deixava títulos e categorias quase invisíveis. A reprodução com o ZIP original no tema Night Mapping confirmou a causa. O problema estava na apresentação, sem relação com CRS, dados ou resultados.

O tema também fornece um delegate de menu para comboboxes. Esse delegate pode desenhar a seleção com suas próprias cores, mesmo quando a paleta da lista já foi alterada. A correção usa o delegate Qt padrão nesses casos e preserva delegates personalizados.

## Estratégia

O módulo `auditoria_aplicacao/aparencia.py` concentra a derivação de cores para fundo, superfícies, cartões, texto, texto secundário, texto desabilitado, bordas, destaque, seleção, hover, foco, aviso, erro e sucesso. As cores partem dos papéis de QPalette da janela QGIS. Cores com contraste insuficiente são aproximadas do extremo claro ou escuro adequado. Não existe dependência do nome do tema Windows nem de uma paleta escura fixa.

As regras são aplicadas somente à subárvore da nova interface. Não modificam a paleta global, o tema configurado, fontes do sistema ou simbologias GIS. As listas suspensas recebem regras próprias por serem janelas Qt separadas. O observador de eventos considera apenas mudanças de aparência da janela principal e a abertura de listas do próprio Auditor.

Os estados selecionados usam fundo e contorno reforçado. O foco tem borda explícita; botões desabilitados têm borda tracejada e texto legível. Campos, listas, menus, cabeçalhos, tooltips e barras de rolagem acompanham as cores apropriadas. Pendências continuam descritas por texto, além da representação visual.

## Mudanças de tema

O componente reage a PaletteChange, ApplicationPaletteChange e StyleChange sem reconstruir formulários. Na API do QGIS 3.44, retornar a `default` remove o stylesheet, mas não repõe integralmente a paleta anterior. Esse caminho pode deixar cores mistas no próprio QGIS; reinicie o QGIS para conferir o tema padrão completo. O Auditor não altera a paleta global para corrigir essa limitação do hospedeiro. Os testes alternaram os temas nativos Night Mapping e padrão em tempo de execução no QGIS 3.44.15, preservando o campo de filtro e o editor ativo. O complemento não força uma alternância nem salva configurações globais.

Se a troca feita pelas preferências da sua instalação pedir reinicialização, siga a orientação do QGIS. A alteração será detectada quando a paleta efetiva mudar ou na próxima abertura. Depois de instalar uma versão nova do complemento, reinicie o QGIS para carregar os módulos atualizados.

## Escopo visual

A correção cobre Preparar, Investigar, Meus trabalhos, inclusão multifonte, atributos, filtros, cartões de categorias e ações secundárias. O histórico, propostas, relatórios e outros formulários especializados continuam usando os controles nativos do QGIS; foram inspecionados nos dois temas. Não foram reescritos seus algoritmos nem a persistência. Os destaques cartográficos mantêm suas cores anteriores.

## Evidências

As capturas são de processos nativos do QGIS 3.44.15 com os ZIPs instalados em perfis isolados. Os dados de rede, projetos e propostas utilizados são sintéticos. A captura operacional mencionada no pedido não estava disponível como arquivo nesta etapa; a comparação utiliza a reprodução controlada com a 1.14.0 preservada.

| Verificação | Evidência |
| --- | --- |
| Problema reproduzido | [1.14.0 no tema escuro](capturas/temas/antes_1_14_0.png) |
| Quadro | [Escuro](capturas/temas/escuro_01_quadro.png) · [Claro](capturas/temas/claro_01_quadro.png) |
| Tubulações | [Escuro](capturas/temas/escuro_03_tubulacoes.png) · [Claro](capturas/temas/claro_03_tubulacoes.png) |
| Equipamentos | [Escuro](capturas/temas/escuro_04_equipamentos.png) |
| Fontes | [Escuro](capturas/temas/escuro_02_fontes.png) |
| Atributos e filtros | [Campos](capturas/temas/escuro_05_campos.png) · [Filtro](capturas/temas/escuro_06_filtro.png) |
| Seleção e ações | [Combobox aberto](capturas/temas/escuro_07_combo_aberto.png) · [Hover e foco](capturas/temas/escuro_08_hover_foco.png) · [Desabilitado](capturas/temas/escuro_09_desabilitado.png) · [Menu](capturas/temas/escuro_13_menu.png) |
| Outras áreas | [Investigar](capturas/temas/escuro_11_investigar.png) · [Trabalhos](capturas/temas/escuro_12_trabalhos.png) |
| Apresentação | [Painel estreito](capturas/temas/escuro_14_estreito.png) · [Janela escura](capturas/temas/escuro_15_independente.png) · [Janela clara](capturas/temas/claro_15_independente.png) · [Maximizada](capturas/temas/escuro_16_maximizada.png) |
| Legado | [Histórico](capturas/temas/escuro_17_historico.png) · [Proposta](capturas/temas/escuro_18_proposta.png) · [Exportação](capturas/temas/escuro_19_exportacao.png) |

## Testes

A suíte completa aprovou 1.304 testes em 38 módulos, preservando os 1.297 anteriores e acrescentando sete regressões de aparência. Após os últimos ajustes de cores e bordas, as sete regressões foram repetidas com sucesso.

O pacote instalado foi exercitado nos dois temas em processos nativos distintos, com cadastro de fontes, campos/filtros, menus, popup, estados de botões, painel estreito, janela independente, maximização, troca de tema com rascunho, histórico, proposta e exportação. O encerramento exigiu `aboutToQuit` e retorno zero; timeout não foi aceito como sucesso.

## Contraste e limitações

A luminância relativa sRGB e a razão de contraste são calculadas sobre os valores RGB utilizados. Textos principais, secundários, desabilitados, selecionados, em hover e mensagens têm alvo mínimo de 4,5:1. Bordas essenciais, foco e indicadores de rolagem têm alvo de 3:1. As regressões incluem paletas claras, escuras e uma paleta com contraste inicialmente insuficiente. A seleção do popup também foi medida na paleta efetiva do controle instalado, além da inspeção da imagem renderizada.


Medições dos tokens utilizados no pacote instalado (razões mínimas, sem arredondar para decidir aprovação):

| Tema | Texto, mínimo | Indicadores, mínimo | Seleção do popup |
| --- | ---: | ---: | ---: |
| Escuro | 4.5002:1 | 3.0034:1 | 4.5214:1 |
| Claro | 4.5038:1 | 3.0257:1 | 4.5038:1 |

Esses cálculos não equivalem a uma certificação de acessibilidade de cada pixel, ícone ou tema de terceiros. Os formulários especializados herdam os estilos nativos e podem depender da qualidade de um tema personalizado. A validação publicada usa os temas padrão e Night Mapping fornecidos com o QGIS; não representa todas as combinações de fontes, DPI e estilos existentes.

As telas claras foram capturadas em uma sessão iniciada em tema claro, antes de alternar para o tema escuro. A troca de aparência foi exercitada separadamente ao final, preservando o rascunho.

O ensaio visual é automatizado pela API Qt e as capturas foram inspecionadas. A aceitação humana no ambiente operacional do usuário continua necessária. Nenhum teste físico de dois monitores é alegado nesta correção.

## Roteiro de aceitação

1. Instale o ZIP 1.14.1 pelo gerenciador de complementos e reinicie o QGIS.
2. Com o tema escuro ativo, abra Redes, Equipamentos, o seletor de campos e o menu de trabalhos. Confira texto, seleção e foco por teclado.
3. Edite um filtro, alterne painel/janela e confirme que o rascunho permanece. Use a rolagem e redimensione a janela.
4. Consulte uma investigação persistida, histórico, proposta e exportações.
5. Repita com o tema claro. Se a mudança de tema exigir reinicialização, salve antes de fechar.

As bases existentes e a release 1.14.0 permanecem disponíveis. Nenhuma etapa nova de aprovação, documentação obrigatória ou identificação pessoal foi introduzida.

## Referências técnicas

[QgsApplication 3.44 e aplicação dos temas](https://api.qgis.org/api/3.44/qgsapplication_8cpp_source.html) · [Paleta e estilos Qt](https://doc.qt.io/qt-6.5/qwidget.html) · [Eventos de mudança de estilo e paleta](https://doc.qt.io/qt-6/style-aware-widgets.html).
