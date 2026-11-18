# Quadro do Modelo — 1.14.0

O Water Network Auditor abre no **Quadro do Modelo**, com quatro grupos da preparação e três áreas de trabalho. O projeto permanece selecionado no cabeçalho. Quando há uma base WaterGEMS associada, o cabeçalho mostra o modelo, o cenário e a perspectiva.

## Preparar minha rede

- **Redes** reúne as fontes de tubulações, inclusive aduções e redes complementares.
- **Equipamentos** permite escolher PRVs, TCVs, FCVs, PBVs, ventosas, hidrantes, registros, bombas, boosters, Reservoirs, Tanks e outros elementos.
- **Áreas** reúne setores, zonas de VRP, zonas de booster e outras zonas de distribuição.
- **Conectividade** registra a estratégia para Junctions existentes, inferência futura ou combinação. A construção da topologia GIS pertence à próxima etapa.

Escolha o grupo e use a ação principal para adicionar camadas. Você pode selecionar várias fontes juntas. Os campos são sugeridos quando a identificação é inequívoca. **Editar detalhes da fonte** abre os atributos e os filtros dentro do inspetor. Campos técnicos adicionais continuam recolhíveis.

Para usar uma camada geral de equipamentos em outra categoria, abra **Mais ações da fonte → Usar esta fonte em outra categoria**. O cadastro reaproveita os campos compatíveis e abre o editor para conferir o filtro da nova categoria. Por exemplo, configure `tipo = PRV` e `tipo = TCV` em classificações distintas. **Conferir fontes** identifica IDs ausentes, repetições e sobreposições.

**Aplicar mapeamento a outras camadas** continua disponível para fontes da mesma categoria. Em **Resumo e revisões**, consulte a composição atual e as configurações anteriores. Fontes auxiliares e intervenções cadastradas também continuam acessíveis pelo menu **⋯ → Cadastro auxiliar e intervenções**.

O botão **Salvar alterações** publica uma revisão do cadastro. Ao alternar de área ou apresentação, o rascunho fica no mesmo editor. Ao trocar de projeto, fechar o painel ou encerrar o QGIS com edições, escolha salvar, descartar ou cancelar.

## Trabalhar com o mapa

Clique na fonte cadastrada para destacá-la. Os itens temporários usam geometrias da camada carregada, transformadas para o CRS do mapa. O filtro da configuração é aplicado. A seleção existente e o renderer da fonte são preservados.

A prévia limita a leitura a 500 feições correspondentes. Uma mensagem informa quando há mais elementos. Selecione feições pela ferramenta de seleção do QGIS, na fonte que está em foco, para consultar identificadores e rótulos. O painel mostra até oito identificações no detalhamento da mensagem.

Use **Enquadrar destaque** para aproximar os elementos destacados e **Limpar** para remover os itens temporários. A troca de fonte atualiza o destaque e conserva o zoom até um comando explícito. Fontes sem geometria, indisponíveis ou com CRS inválido apresentam uma orientação. Coordenadas WaterGEMS continuam dependentes da validação espacial existente.

## Investigar minha rede

Escolha o objetivo da análise. A versão disponibiliza consulta topológica, corredores alimentadores e acesso à investigação integrada existente. Nesta investigação permanecem disponíveis as travessias, os dispositivos próximos, as correspondências, as observações, as propostas, os filtros e as exportações.

As ações encaminham aos motores e interfaces existentes. Se um requisito estiver ausente, a ferramenta orienta sua preparação. A navegação anterior está em **⋯ → Ferramentas avançadas**. O roadmap permanece indicado como informação, com topologia GIS, zonas topológicas e isolamento por válvulas previstos.

## Meus trabalhos

A lista reúne as auditorias GIS, as investigações e as topologias vinculadas ao projeto. Pesquise pelo nome, projeto ou modelo, escolha o tipo e use **Abrir trabalho**. Arquivos de backup técnico e bases arquivadas ficam no catálogo de recuperação.

Ocorrências, decisões, propostas e Selection Sets pertencem à investigação aberta. Use **Histórico, conjuntos e exportações** para consultar esses registros, gerar relatórios, exportar acompanhamento ou comparar versões. A localização de elementos utiliza os destaques da própria investigação e exige geometria confiável.

## Projeto, cenário e apresentação

O seletor de projeto fica no cabeçalho. O menu **⋯** permite criar um projeto e preparar uma base WaterGEMS. O seletor de cenário mostra versões persistidas correspondentes ao modelo e ao projeto ativos. **Outros cenários / preparar versão** dá acesso ao explorador existente. A escolha passa pelas verificações de identidade e pelas guardas de rascunhos. As decisões continuam ligadas à execução, ao cenário e à perspectiva em que foram registradas.

Escolha **Painel integrado** ou **Janela independente** no cabeçalho. A mesma instância acompanha a navegação. O mecanismo de preferências preserva a geometria, o monitor e a maximização e ajusta a janela quando a tela anterior está ausente.

## Atualização e aceitação

Instale o ZIP pelo gerenciador de complementos do QGIS e reinicie o QGIS para carregar os módulos da nova versão. A 1.13.1 continua disponível no GitHub para comparação e retorno.

Roteiro recomendado no seu projeto:

1. Abra o complemento e confira projeto e cenário.
2. Em Redes, cadastre três fontes de uma vez. Confira campos sugeridos.
3. Reaproveite uma fonte de equipamentos em PRV e TCV, com filtros separados.
4. Cadastre uma zona e registre a estratégia de Junctions.
5. Destaque uma rede e selecione uma feição no QGIS. Confira sua identificação e preserve o zoom.
6. Salve. Abra uma investigação existente por Meus trabalhos, consulte uma proposta e localize seus elementos.
7. Volte ao Quadro, altere um filtro e troque entre painel e janela. Salve, reinicie e confira a revisão.

As imagens e o ensaio publicado usam dados sintéticos. A aceitação humana com um projeto operacional e monitores físicos permanece pendente. As fontes cadastradas são a configuração central do projeto, enquanto as ferramentas antigas de processamento continuam utilizando seus formulários durante a migração da apresentação.
## Capturas e comparação visual

As capturas foram obtidas no QGIS 3.44.15 com o ZIP instalado em perfil isolado, usando arquivos GIS sintéticos e uma investigação persistida sintética.

| Fluxo | Capturas |
| --- | --- |
| Entrada e preparação | [Tela inicial](capturas/nova_interface/01_entrada.png) · [Quadro](capturas/nova_interface/02_quadro.png) · [Redes](capturas/nova_interface/03_redes.png) |
| Categorias e atributos | [Equipamentos](capturas/nova_interface/04_equipamentos.png) · [Áreas](capturas/nova_interface/05_areas.png) · [Conectividade](capturas/nova_interface/06_conectividade.png) · [Inclusão em lote](capturas/nova_interface/07_multifonte.png) · [Campos](capturas/nova_interface/08_campos.png) |
| Mapa | [Tubulações](capturas/nova_interface/09_destaque_rede.png) · [Setor](capturas/nova_interface/10_setor.png) · [Ocorrência persistida](capturas/nova_interface/19_ocorrencia_no_mapa.png) |
| Investigação e trabalhos | [Investigar](capturas/nova_interface/11_investigar.png) · [Meus trabalhos](capturas/nova_interface/12_trabalhos.png) · [Histórico](capturas/nova_interface/13_historico.png) · [Proposta recuperada](capturas/nova_interface/18_proposta_recuperada.png) |
| Apresentação | [Painel estreito](capturas/nova_interface/14_estreito.png) · [Janela independente](capturas/nova_interface/15_independente.png) · [Maximizada](capturas/nova_interface/16_maximizada.png) · [Após reiniciar](capturas/nova_interface/17_reabertura.png) |
| Versão anterior | [Cadastro na 1.13.1](capturas/modelo_gis_1_13_1/03_tubulacoes.png) · [Campos na 1.13.1](capturas/modelo_gis_1_13_1/05_mapeamento_automatico.png) |

A navegação principal passou das abas de módulos da Central anterior para três intenções de trabalho. O cadastro começa no quadro de quatro grupos. A seleção e a edição continuam no painel, com retorno ao grupo e preservação do rascunho. Os formulários de análises e histórico existentes permanecem acessíveis nos contextos apropriados.

O ensaio de sete fontes exigiu 39 ações lógicas registradas, incluindo a revisão de atributos, a reutilização de uma camada em três categorias, a construção de três filtros e a gravação de uma revisão. O protótipo B usou 24 ações com fontes previamente separadas e dados demonstrativos. Essa diferença reflete configurações reais adicionais e impede tratar os dois números como equivalência de esforço. A inclusão das três redes ocorreu em lote e exigiu seis ações a partir do Quadro já aberto.

## Arquitetura de apresentação

A nova entrada deriva da Central para reaproveitar a mesma instância de projeto, os requisitos e os encaminhamentos existentes. O cadastro multifonte permanece como a única fonte de configuração. O Quadro reúne esse cadastro em quatro grupos e usa seus editores, filtros e persistência. Os destaques são itens temporários do canvas e as leituras de feições usam snapshots com limite e worker cancelável.

A ação de salvar permanece explícita para permitir que alterações em fontes e filtros formem uma revisão coerente. A compatibilidade de identificação, CRS e dados hidráulicos continua sendo verificada pelos respectivos serviços. Os arquivos GIS e WaterGEMS de entrada são usados em modo de leitura.

## Validação da pré-release

Foram aprovadas 1.297 verificações automatizadas em 37 módulos no ambiente Python do QGIS 3.44.15. O total consolida a suíte completa e a repetição final das 16 regressões da nova apresentação. Os 1.281 testes anteriores foram preservados; duas expectativas de navegação foram atualizadas para a nova entrada.

O ZIP foi instalado em perfil isolado e exercitado em dois processos nativos do QGIS, com dados sintéticos. O ensaio cadastrou sete fontes, configurou filtros independentes de equipamentos, destacou geometrias reais, recuperou uma proposta persistida, localizou a ocorrência e reabriu o cadastro e suas revisões após reiniciar. Ambos os processos emitiram `aboutToQuit` e terminaram com código zero. As assinaturas dos arquivos GIS de entrada permaneceram iguais.

As capturas são da aplicação instalada, com ações automatizadas pela API Qt e revisão das imagens. Houve detecção e movimentação para outra tela exposta pelo Qt, sem ensaio humano físico de dois monitores. Isso não substitui a aceitação manual em resoluções, escalas DPI e projetos operacionais do usuário.

### Limitações desta entrega

- A nova apresentação cobre a entrada, o cadastro e a navegação contextual. Os visualizadores de investigação, histórico, cenários e exportações existentes continuam sendo usados quando abertos pelo novo ambiente.
- O quadro consulta as fontes do Modelo GIS. Formulários antigos de processamento ainda mantêm suas próprias seleções; a migração integral desses formulários não foi concluída nesta entrega.
- O destaque de fontes é uma prévia limitada. Para grandes camadas, use seleção de feições e o detalhamento; não interprete o enquadramento da amostra como extensão completa da rede.
- A estratégia de inferência de Junctions é somente registrada. Nenhum nó ou conexão é gerado nesta versão.
- A comparação de 39 ações reais com 24 no protótipo não comprova redução de esforço; as tarefas tinham configurações distintas. Uma avaliação humana com entradas equivalentes permanece necessária.
