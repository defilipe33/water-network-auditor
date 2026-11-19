# Ajustes funcionais do Modelo GIS — 1.14.3

Esta correção mantém o Quadro do Modelo, o cadastro multifonte e a execução sob demanda da 1.14.2. Não constrói topologia GIS nem modifica modelos WaterGEMS.

## Diagnóstico e componentes reaproveitados

O código anterior aplicava explicitamente a mesma cor aos estados selecionado e hover dos popups/views. Também chamava `itemDelegate().metaObject()` sem verificar ausência ou destruição do delegate. Os novos rótulos são somente apresentação; não alteram chaves ou valores persistidos.

A revisão das capturas identificou ainda que combinar filtro por FID com expressão no mesmo `QgsFeatureRequest` substituía a seleção. O destaque agora restringe os FIDs e avalia a expressão nesse subconjunto, carregando os atributos necessários. Uma regressão exige uma única geometria ao escolher uma única feição da amostra.

Foram reaproveitados `modelo_gis.py`, suas revisões, o painel multifonte, o gerenciador de atividades/workers, o destaque temporário e a apresentação painel/janela. Condições visuais e declarações GIS são componentes separados da interface. Não há segundo cadastro ou histórico paralelo.

## Identificação e aparência

Os campos passam a se chamar **ID da feição**, **Nome exibido**, **Campo de correspondência WaterGEMS** e **Identificador correspondente no WaterGEMS**. As chaves persistidas continuam `id`, `label` e `wg`. FID é uma referência do provedor usada apenas na navegação da sessão; não substitui o identificador cadastral.

Na categoria PRV, **Nome** é opcional e distinto de Nome exibido. NOME, NAME e NOME_VRP são candidatos; mais de um candidato exige escolha. TAG não é associado automaticamente. Um TAG pode ser escolhido manualmente quando seu significado corresponder ao nome. O valor mapeado aparece na amostra e nos detalhes cartográficos, ficando preservado para futuras ferramentas.

A aparência diferencia seleção persistente, hover suave e desabilitado, com cores derivadas da paleta QGIS. O tratamento de popups verifica a existência e o ciclo de vida do delegate e da view. Delegates personalizados são preservados; somente os delegates nativos de combo incompatíveis recebem o delegate padrão Qt. Uma view explicitamente sem delegate permanece assim.

## Filtrar elementos

Abra **Configurar campos e filtro → Filtrar elementos**. O construtor é criado apenas ao expandir a seção.

1. Selecione um campo, operador e valor.
2. Use **Adicionar condição**.
3. Repita para outras condições. Cada grupo combina seus itens com E ou OU.
4. Para misturar conectivos, crie um subgrupo e escolha seu conectivo explicitamente.
5. Use **Usar condições no filtro**, consulte a amostra e aplique à fonte.

É possível atualizar ou remover uma condição selecionada. Texto, número, data e booleano possuem operadores apropriados. Datas utilizam AAAA-MM-DD; datas com horário utilizam AAAA-MM-DDTHH:MM:SS. Intervalos possuem dois valores. Na operação de lista, acrescente cada valor pelos controles; não é necessário escrever uma expressão ou lista técnica.

**Consultar valores existentes** é opcional: examina até 250 feições do campo escolhido em worker, sem ler todos os campos nem executar uma contagem global. A lista pode ser parcial. É permitido digitar valores que não apareçam nela.

O texto persistido continua sendo uma expressão QGIS validada. Um ensaio do QGIS 3.44 retornou NULL em uma combinação OR repetindo um campo textual com espaço no nome; para esse caso, o gerador utiliza `to_string` explícito, preservando texto e nulos. A expressão antiga não é reescrita por essa regra. Campos, literais e grupos são construídos com regras tipadas e quoting do QGIS. Nulos são distintos de textos vazios. Apóstrofos e caracteres de curinga textuais são tratados como dados.

### Filtros anteriores

Abrir o construtor não converte nem altera a expressão antiga. Ela permanece no **Modo especialista — expressão QGIS**. Aplicar condições visuais substitui explicitamente o filtro da fonte no rascunho. Salvar registra uma nova revisão; a anterior continua acessível. Não há substituição textual para tentar reconstruir uma árvore visual a partir de uma expressão arbitrária.

Ao salvar ou consultar uma amostra com condições adicionadas ainda não aplicadas, o programa valida e gera a expressão dessas condições. Um grupo vazio ou valor incompatível impede somente essa aplicação, preservando o rascunho.

## Verificar elementos encontrados

A ação exibe até **20 correspondências**, com ampliação sob demanda para até 100. Cada consulta examina no máximo 5.000 feições. A consulta interrompe a leitura quando atinge o tamanho da amostra ou o limite de exame. Isso pode produzir uma amostra vazia parcial em um filtro muito seletivo; não significa que a camada inteira não tenha resultados.

O retorno distingue quantidade exibida, feições examinadas, total conhecido por término da leitura e total ainda não calculado. Filtros inválidos têm mensagem própria; zero só é apresentado como total quando a consulta terminou integralmente. O cancelamento usa os workers e o painel de atividades existentes.

Selecione uma linha e use **Destacar elemento da amostra**. O destaque é temporário; **Enquadrar elemento destacado** aproxima somente por ação explícita. **Limpar destaque** remove a representação temporária. A seleção e o renderer originais não são alterados. Mudanças de filtro ou fonte invalidam a amostra; um retorno atrasado de outro filtro não é aplicado.

## Conexões declaradas de Reservoirs e Tanks

No editor da fonte de Reservoir ou Tank, expanda **Definir conexões com a rede**.

1. No QGIS, selecione exatamente um equipamento dessa fonte e uma ou mais tubulações GIS cadastradas.
2. Os elementos precisam de ID da feição mapeado, não nulo e inequívoco dentro do filtro da fonte. Não é usado FID como identidade persistente.
3. Informe início cadastral, fim cadastral, posição intermediária ou desconhecida. Esses termos não indicam sentido de vazão.
4. Use **Declarar conexão com a seleção QGIS**. A conferência dos IDs ocorre em worker, por snapshots de leitura.
5. Aplique à fonte e salve o Modelo GIS.

A distância entre equipamento e tubulação não impede a declaração. Isso atende equipamentos GIS cujo ponto foi derivado de um polígono, sem supor desconexão hidráulica.

Cada declaração tem UUID, referências tipadas de equipamento/tubulações, fontes e assinaturas, posição, natureza `DECLARADA_MANUALMENTE`, data e situação. A revisão do Modelo GIS é o contexto de salvamento. Substituir uma relação registra referência à anterior; remover cria evento lógico, sem apagar seu histórico. A interface lista as relações vigentes.

Use **Conferir relações nas fontes atuais** após atualizar dados externos. Fonte ausente, identidade alterada, ID removido ou repetido tornam a relação pendente de revisão. Não há remapeamento por proximidade nem equivalência automática por Label. A verificação de presença do ID não comprova a conexão hidráulica.

A infraestrutura persiste no mesmo cadastro e mecanismo de revisões, como extensão opcional de cada fonte. Configurações antigas continuam válidas sem esse campo. O editor aceita até 100 elementos selecionados por fonte em uma declaração. Associação a múltiplas tubulações é permitida. Não há obrigação de equivalência de um equipamento GIS com um único elemento WaterGEMS.

**Limites:** não há novo grafo, divisão de tubulações, snap, conexão inferida, ajuste de coordenadas ou tradução automática do arranjo Reservoir/FCV/Tank. Posição intermediária ainda não possui uma medida linear detalhada. Esses contratos deverão ser consumidos e reconciliados conservadoramente na futura etapa de topologia GIS.

## Polígonos e investigação independente

Setores e zonas são referências espaciais GIS. Podem ser cadastrados sem qualquer correspondência WaterGEMS. Estar dentro de um polígono não comprova pertencimento hidráulico. Nenhuma exportação hidráulica nova de polígonos é introduzida; as saídas cartográficas existentes continuam disponíveis.

Em **Investigar minha rede**, Verificar modelo, Zonas e fronteiras e Interferências abrem a auditoria geométrica GIS existente, sem exigir WaterGEMS. Essa interface ainda pode solicitar suas entradas próprias; não se afirma que exista uma nova topologia GIS. A consulta topológica e os corredores existentes usam WaterGEMS e permanecem identificados assim. Intervenções existentes pertencem à investigação integrada. Corredores GIS, zonas topológicas e planejamento sobre nova topologia são funções futuras.

## Validação e desempenho

Foram aprovados **1.361 testes em 40 módulos**: os 1.320 anteriores e 41 novas regressões. A suíte integral foi executada em processos isolados PyQGIS; os cinco módulos afetados foram reexecutados após os ajustes finais, incluindo invalidação de retorno atrasado após mudança de fonte. Não houve remoção de testes anteriores.

O ZIP foi instalado em perfil isolado no QGIS 3.44.15, Windows 64 bits e Python 3.12.15. A automação Qt exercitou seleção/hover, filtros, 20 correspondências, mapa, Nome de PRV, declaração de conexão de reservatório afastado, áreas sem vínculo WaterGEMS, painel, janela independente e reabertura em outro processo. Os três processos finais (escuro, claro e reabrir) terminaram com retorno zero e `aboutToQuit`. Hashes das fontes sintéticas foram preservados.

As cores medidas na lista foram: escuro, seleção #d7801a e hover #50402e; claro, seleção #0078d7 e hover #d1e7f8. A medição de pixels considera a escala DPI. As capturas foram revisadas; não se trata de aceitação humana operacional ou de teste físico em dois monitores.

Durante o desenvolvimento, rodadas interrompidas por configuração incorreta do roteiro e falhas no próprio encerramento do ensaio foram registradas como falha/timeout, sem contar como aprovação. O roteiro foi corrigido e repetido sobre o pacote final. Nenhum timeout foi considerado encerramento bem-sucedido.

Comparação sequencial dos ZIPs instalados, com o mesmo roteiro sintético da 1.14.2. Os cenários A/B/C são vazio, 18 fontes com 66.600 feições, e essas fontes com cadastro/histórico/bases sintéticas. Tempos em ms, incluindo despacho Qt; p95 inclui todas as amostras.

| Tema | Cenário | Operação | Mediana 1.14.2 | Mediana 1.14.3 | p95 antes | p95 depois |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| escuro | A_vazio | alternar_categorias | 18.2 | 24.2 | 26.0 | 31.7 |
| escuro | A_vazio | preparar | 16.7 | 15.9 | 18.5 | 18.8 |
| escuro | A_vazio | investigar | 15.9 | 15.9 | 29.5 | 17.3 |
| escuro | A_vazio | trabalhos | 15.7 | 15.8 | 43.5 | 36.3 |
| escuro | B_multifonte | alternar_categorias | 25.3 | 24.0 | 28.7 | 36.0 |
| escuro | B_multifonte | preparar | 5.5 | 15.8 | 26.2 | 18.9 |
| escuro | B_multifonte | investigar | 9.9 | 15.6 | 19.0 | 29.9 |
| escuro | B_multifonte | trabalhos | 10.0 | 16.0 | 26.7 | 26.5 |
| escuro | B_multifonte | campos_filtros | 179.2 | 147.9 | 193.0 | 163.8 |
| escuro | C_integrado | alternar_categorias | 26.5 | 22.3 | 62.1 | 45.7 |
| escuro | C_integrado | preparar | 15.9 | 15.7 | 31.4 | 31.1 |
| escuro | C_integrado | investigar | 15.7 | 15.7 | 31.8 | 45.7 |
| escuro | C_integrado | trabalhos | 15.7 | 15.7 | 39.5 | 36.8 |
| escuro | C_integrado | campos_filtros | 176.0 | 164.9 | 189.1 | 173.5 |
| claro | A_vazio | alternar_categorias | 16.0 | 18.5 | 31.7 | 32.3 |
| claro | A_vazio | preparar | 16.0 | 15.8 | 16.9 | 18.1 |
| claro | A_vazio | investigar | 15.9 | 15.8 | 21.3 | 25.8 |
| claro | A_vazio | trabalhos | 15.8 | 15.9 | 33.6 | 35.9 |
| claro | B_multifonte | alternar_categorias | 23.7 | 22.3 | 26.4 | 29.0 |
| claro | B_multifonte | preparar | 15.9 | 15.9 | 17.0 | 18.1 |
| claro | B_multifonte | investigar | 15.7 | 15.9 | 20.0 | 19.7 |
| claro | B_multifonte | trabalhos | 15.1 | 15.8 | 25.5 | 34.6 |
| claro | B_multifonte | campos_filtros | 84.1 | 83.0 | 100.9 | 104.1 |
| claro | C_integrado | alternar_categorias | 22.3 | 30.8 | 42.2 | 74.9 |
| claro | C_integrado | preparar | 16.6 | 15.7 | 31.9 | 42.0 |
| claro | C_integrado | investigar | 16.0 | 15.8 | 27.5 | 63.0 |
| claro | C_integrado | trabalhos | 14.7 | 16.0 | 47.6 | 42.6 |
| claro | C_integrado | campos_filtros | 88.9 | 112.1 | 103.7 | 129.8 |

Os dados completos, primeira amostra, pior caso e contadores estão no [JSON revisado](metricas/ajustes_1_14_3.json). As metas não são garantias universais. O ciclo de categorias e o editor (construir/cancelar) são operações compostas. A comparação não mede a consulta nova de amostras ou a conferência de associações como se fossem funções da versão anterior.

A instrumentação e o ambiente são os mesmos descritos no [guia de desempenho](DESEMPENHO_1_14_2.md). Demais aplicações abertas e caches do sistema podem variar. Não foi obtida medição confiável de RAM/I/O físico; não houve teste humano físico em dois monitores. O carregamento sob demanda da Central legada permanece.

### Capturas reais revisadas

| Verificação | Evidência |
| --- | --- |
| Seleção persistente, hover e selecionado sob o mouse | [Selecionado](capturas/ajustes_gis/selecionado_escuro.png), [hover escuro](capturas/ajustes_gis/hover_escuro.png), [selecionado com hover](capturas/ajustes_gis/selecionado_hover.png), [hover claro](capturas/ajustes_gis/hover_claro.png) |
| Construtor, duas condições e expressão gerada | [Componente Qt expandido](capturas/ajustes_gis/construtor.png) |
| 20 correspondências, limite e contagem explícitos | [Amostra](capturas/ajustes_gis/amostra.png) |
| Uma feição selecionada na amostra | [Exatamente uma geometria no mapa](capturas/ajustes_gis/mapa.png) |
| Nome opcional de VRP, distinto dos IDs | [Mapeamento](capturas/ajustes_gis/nome_vrp.png) |
| Reservoir, relação manual e lista vigente | [Editor expandido](capturas/ajustes_gis/reservatorio.png), [relação no painel](capturas/ajustes_gis/relacao_no_painel.png) |
| Áreas de referência, sem WaterGEMS | [Zona de VRP](capturas/ajustes_gis/areas.png) |
| Investigação GIS sem modelo hidráulico | [Entrada de investigação](capturas/ajustes_gis/investigar_gis.png) |
| Apresentação e persistência | [Painel](capturas/ajustes_gis/painel.png), [janela independente](capturas/ajustes_gis/independente.png), [reabertura](capturas/ajustes_gis/reabertura.png) |


## Roteiro de aceitação operacional

Instale o ZIP 1.14.3 pelo gerenciador de complementos e reinicie o QGIS. A 1.14.2 permanece disponível.

- Em uma cópia do projeto, selecione a primeira fonte e passe o mouse sobre outra; depois sobre a selecionada. Confirme que a seleção não mudou.
- Abra e feche seletores repetidamente e consulte a amostra, nos dois temas.
- Abra uma fonte antiga e confira IDs, mapeamentos e expressão preservados.
- Configure Nome de PRV, deixando TAG distinto, e confira os valores na amostra.
- Crie `(TIPO = PRV OU TIPO = TCV) E SITUACAO = ATIVA` visualmente; confira a expressão gerada e os elementos amostrados.
- Teste intervalo numérico, texto com apóstrofo, datas, nulo, vazio e filtro sem resultados.
- Destaque, enquadre e limpe uma feição sem modificar a seleção original.
- Selecione um reservatório afastado e tubulações cadastradas, declare, salve, reabra, substitua e remova logicamente a relação. Confira as revisões.
- Atualize uma cópia da fonte removendo um ID; use Conferir relações e confirme a pendência, sem transferência automática.
- Cadastre áreas sem WaterGEMS, alterne painel/janela e confirme a preservação dos rascunhos.
- Feche e reabra o QGIS. Confira o cadastro e compare os hashes das fontes originais.

Não há aprovação formal, responsável, documento ou aceite obrigatório. Não foram modificados dados hidráulicos, Active Topology, algoritmos de conectividade ou arquivos originais.


## Limitações de apresentação e interpretação

Formulários extensos e tabelas utilizam rolagem em painéis baixos; os 20 registros não precisam estar simultaneamente visíveis. Capturas de componentes expandidos são renderizações dos widgets Qt reais do pacote instalado, não mockups. A inferência de Junctions, um grafo GIS independente e a interpretação hidráulica das conexões declaradas permanecem fora desta entrega.


A comparação de navegação manteve tempos baixos nas operações simples, mas não melhorou todos os resultados: no cenário integrado claro, o ciclo das quatro categorias passou de 22,3 para 30,8 ms e o ciclo de construir/cancelar o editor de 88,9 para 112,1 ms. No integrado escuro, as mesmas operações passaram de 26,5 para 22,3 ms e de 176,0 para 164,9 ms. Esses custos e a variação de p95 estão publicados, sem afirmar ganho universal.
