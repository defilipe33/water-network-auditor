# Modelo GIS do Projeto — Etapa 1

O Water Network Auditor usa o QGIS para preparar dados, investigar a rede e propor intervenções. A consolidação e a simulação hidráulica continuam no WaterGEMS. A versão 1.13.0 acrescenta o cadastro multifonte por projeto como base para as próximas etapas.

## Configurar no QGIS

1. Abra ou crie um projeto de trabalho. Carregue as camadas GIS no QGIS.
2. Em **Central de Trabalho → Configurar Modelo GIS**, use **Adicionar fonte** para escolher uma camada e sua categoria.
3. Selecione o identificador cadastral. Quando houver associação planejada, configure o campo GIS e o atributo WaterGEMS correspondente. Os dois são opcionais. Consulte **Atributos técnicos e classificação** para mapear atributos adicionais.
4. Repita para cada fonte. Para separar válvulas de uma mesma camada, cadastre-a em PRVs e TCVs, por exemplo, com filtros independentes como `"TIPO" = 'PRV'` e `"TIPO" = 'TCV'`.
5. Escolha como obter os nós futuramente. **Inferir nós a partir das tubulações** pode ser registrado sem nenhuma camada pontual.
6. Use **Conferir fontes** para examinar as contagens, os identificadores ausentes ou repetidos e as feições que atendem a mais de uma configuração. Salve diretamente com **Salvar Modelo GIS**. Cadastros parciais podem ser retomados depois.

A Central apresenta a revisão atual, o total por categoria e a estratégia de nós. A aba **Modelo GIS** mostra a disponibilidade de cada fonte. O mesmo rascunho acompanha a alternância entre painel acoplado e janela independente. Ao trocar de projeto ou sair do QGIS com um rascunho, escolha salvar, descartar ou cancelar.

### Categorias

| Grupo | Categorias |
| --- | --- |
| Redes | Tubulações de distribuição, adução, complementares e outras, com papel existente, projetado, proposto ou de referência |
| Nós | Junctions e nós GIS |
| Reservatórios e bombas | Reservoirs, Tanks, pontos de entrada, bombas e boosters/instalações |
| Válvulas e equipamentos | PRV, TCV, FCV, PBV, ventosa, hidrante, registro de bloqueio e outros dispositivos |
| Zonas e setores | Setor de abastecimento, zona de VRP, zona de booster e outras zonas |
| Intervenções | Referências de intervenções |
| Auxiliares | Arruamento, limite administrativo, ortofoto e outras camadas |

As categorias determinam as geometrias aceitas e os atributos que podem ser mapeados. Polígonos de booster podem representar instalações. Cada camada conserva seu CRS.

## Recuperar uma fonte

Abra o projeto QGIS com as camadas carregadas. O complemento procura o provedor e a URI cadastrados, usando o ID da camada QGIS para distinguir visualizações da mesma fonte. Para um arquivo movido, carregue a camada na nova localização e escolha **Relocalizar**. A conferência compara provedor, geometria, CRS, esquema, subconjunto e tabela de origem. Quando as marcas do arquivo não comprovam a mesma origem física, a configuração relocalizada permanece com **identidade por conferir**.

Camadas temporárias têm identidade restrita à sessão. Para retomá-las após reiniciar, salve a camada em uma fonte persistente e cadastre-a na revisão seguinte. Fontes indisponíveis continuam no cadastro e nas revisões em que foram usadas.

## Arquitetura e versionamento

- `contexto_trabalho.Projetos` continua como índice de projetos. A chave opcional `modelo_gis` preserva um UUID e revisões encadeadas, com data UTC, estratégia de Junctions, configurações completas e IDs das fontes alteradas. A gravação usa arquivo temporário e substituição atômica do próprio índice.
- `modelo_gis.py` mantém o catálogo, a configuração individual e a conferência. Cada configuração tem UUID. A origem é registrada por provedor e URI com subconjunto, esquema e marca local quando disponível. A chave cadastral original e o alvo WaterGEMS são campos distintos. O FID fica restrito à leitura de feições do QGIS.
- `modelo_gis_ui.py` integra a edição à Central, reutilizando as atividades e o controle de apresentação. A conferência lê somente atributos e reutiliza um snapshot para configurações que compartilham a mesma fonte. A leitura acontece em worker com cancelamento cooperativo. A abertura inicial do complemento não varre feições. [Referência PyQGIS do snapshot](https://api.qgis.org/api/3.44/classQgsVectorLayerFeatureSource.html).
- **Consultar alterações** recupera os mapeamentos e filtros de cada revisão. Revisões posteriores registram as auditorias GIS e investigações vinculadas como candidatas a conferência. O impacto preciso depende do uso futuro das fontes em cada análise. Os resultados históricos continuam disponíveis pelos fluxos próprios.
- O cadastro salva somente referências e configuração. As auditorias, investigações e bases antigas continuam com seus formulários e arquivos existentes. Nenhum algoritmo de geometria, integração ou leitura WaterGEMS foi substituído.

## Limites desta entrega

A assinatura de cadastro combina referência e metadados. A comprovação da igualdade de conteúdo ao copiar arquivos entre volumes exige evidência adicional. A conferência de identificadores é feita nas feições que passam pelos filtros. A correspondência com o WaterGEMS será verificada pelas ferramentas que usarem esse vínculo.

As etapas seguintes permanecem no roadmap: construção e revisão da topologia GIS, exportação multielemento ModelBuilder, redes estruturantes e zonas, intervenções e histórico unificado.

## Validação e capturas no QGIS 3.44.15

As capturas foram feitas no QGIS Desktop com o ZIP instalado em um perfil isolado e um projeto sintético. O ensaio exercitou três fontes de tubulações, PRVs e TCVs extraídas por filtros de uma mesma camada, uma fonte poligonal e duas revisões sem camada pontual de Junctions. A escala foi 1,875 reportada pelo Qt em uma área útil lógica de 1024 × 602. As tabelas oferecem rolagem nas duas direções e as ações de gravação ficam fora da área rolável.

| Fluxo | Capturas |
| --- | --- |
| Entrada e fontes | [Central](capturas/modelo_gis/01_central.png) · [Cadastro inicial](capturas/modelo_gis/02_cadastro_inicial.png) · [Três fontes de tubulações](capturas/modelo_gis/03_tubulacoes_multifonte.png) · [Mesma camada em PRV e TCV](capturas/modelo_gis/04_multicategoria.png) |
| Mapeamento e salvamento | [Mapeamento individual](capturas/modelo_gis/05_campos.png) · [Estratégia sem Junctions](capturas/modelo_gis/06_nos_sem_junctions.png) · [Configuração parcial](capturas/modelo_gis/07_configuracao_parcial.png) · [Conferência](capturas/modelo_gis/08_conferencia.png) · [Revisão salva](capturas/modelo_gis/09_salvamento.png) |
| Retomada | [Após reiniciar](capturas/modelo_gis/10_recuperado_apos_reiniciar.png) · [Painel acoplado](capturas/modelo_gis/11_painel_integrado.png) · [Janela independente com rascunho](capturas/modelo_gis/12_janela_independente.png) |

### Roteiro de aceitação com um projeto do usuário

1. Abra um `.qgz` com pelo menos duas redes e uma camada de válvulas. Cadastre as redes, use a camada de válvulas para duas categorias com filtros distintos e adicione um setor.
2. Use **Conferir fontes**. Cadastre um filtro que se sobreponha a outro e confira o aviso. Remova a sobreposição do rascunho, escolha a estratégia de inferência e salve.
3. Altere um mapeamento, troque para janela independente e volte ao painel. Confira o rascunho e salve a segunda revisão. Abra **Consultar alterações** e confira a primeira.
4. Reinicie o QGIS e abra o mesmo `.qgz`. Verifique a revisão, os filtros, a associação WaterGEMS e os estados das fontes.
5. Em uma cópia de teste, carregue um arquivo movido e use **Relocalizar**. Confira a identificação do arquivo ou a indicação de identidade pendente.
6. Abra uma auditoria e uma investigação existentes pelos atalhos da Central. Confirme que seus históricos e resultados continuam acessíveis.

A aceitação humana em um projeto operacional permanece pendente.
