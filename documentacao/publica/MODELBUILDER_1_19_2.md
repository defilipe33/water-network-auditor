# Corrigir e preparar um pacote multielemento no ModelBuilder

## Validar e corrigir no QGIS

A 1.19.1 diagnosticava o retorno ao mesmo nó e permitia cortar anéis simples como opção geral. A 1.19.2 acrescenta decisões revisáveis por segmento, vinculadas à execução e à geometria conferida.

Em **Investigar minha rede → Exportar modelo para WaterGEMS**, selecione uma execução. Avance até **Validação e exportação**, clique em **Validar** e abra **Corrigir pendências topológicas**. Use **Anterior**, **Próxima** e **Aproximar e destacar** para examinar cada caso. A prévia mostra o traçado original em cinza, os segmentos propostos em verde tracejado e os nós antes e depois. **Aplicar** registra a decisão. **Manter pendente** guarda a observação. **Reverter** registra nova revisão.

| Diagnóstico | Tratamento |
| --- | --- |
| Anel simples com mesmo nó nas duas pontas | Pode ser cortado no ponto médio, em posição escolhida no mapa ou em nó que já tenha porta comprovada na mesma parte. A divisão vale para o pacote e conserva o comprimento geométrico e o Pipe físico de origem. |
| Pontas diferentes no mesmo nó | A separação guiada é oferecida para um Pipe de segmento único, com duas portas no nó, sem terceiros ligados. O assistente registra uma hipótese derivada, cuja conectividade precisa ser executada e selecionada antes de exportar. A hipótese original permite retornar à interpretação anterior. |
| Nó compartilhado, relação declarada conflitante ou posição ambígua | Abra a conectividade e revise as portas, a conexão declarada, o ponto complementar ou a geometria associada. A decisão fica pendente até a revisão. |
| Nó, referência ou geometria ausente | Consulte o diagnóstico completo, confira a execução e restabeleça a referência na origem ou na hipótese correspondente. |

**Revalidar elemento** confere um anel escolhido. **Revalidar cadastro completo** retorna à validação abrangente. As revisões são anexadas ao GeoPackage complementar e preservadas pelo arquivo `.wna`. Os arquivos de entrada e os modelos WaterGEMS permanecem em leitura.

## Destino e campos das extremidades

Na etapa final, digite ou cole um caminho absoluto ou escolha a pasta em **Procurar**. Para um projeto `.wna`, a primeira sugestão é `exportacoes` ao lado do manifesto. A pasta escolhida é recuperada no mesmo projeto. A tela indica o nome da subpasta exclusiva. Quando for necessário criá-la, a confirmação se refere à pasta pai. Depois de exportar, use **Abrir pasta do pacote** ou **Copiar caminho**.

`label_no_A` e `label_no_B` são os Labels de `MB_INICIO` e `MB_FIM` no mesmo pacote. Os campos têm dez caracteres e mantêm esses nomes no Shapefile, no GeoPackage e no cabeçalho CSV. O dicionário Shapefile registra os demais nomes físicos. `no_a` e `no_b` são os identificadores técnicos e `MB_TIPO_A` e `MB_TIPO_B` indicam os tipos preparados. No GeoPackage e CSV, as chaves antigas `mb_inicio`, `mb_fim` e `mb_tipo_a/b` conservam a convenção da 1.19.1.

## Preparar os equipamentos

Em **Elementos e atributos**, selecione as categorias desejadas e mapeie os campos. No Modelo GIS, use **Definir conexões com a rede** para declarar vínculos. Uma relação de ponta identifica a parte e a extremidade. Uma relação intermediária deve identificar univocamente a parte do Pipe. Nesse caso o ponto cadastrado precisa coincidir, dentro da tolerância da validação, com o interior do segmento. Se a instalação exigir um nó, o pacote pode dividir a geometria nesse ponto sem editar a camada. Havendo uma divisão válida na posição, o pacote pode reaproveitar o nó.

| Tipo | Saída e pré-requisito |
| --- | --- |
| Junction, Reservoir e Tank | Camadas próprias. Reservoir e Tank usam a porta declarada, geometria coincidente e carga ou níveis mapeados. |
| Hydrant e Air Valve | Camadas pontuais próprias, elevação mapeada e nó com vínculo declarado. A ventosa desta preparação usa duas tubulações incidentes. |
| PRV, PSV, PBV, TCV e FCV | Camadas pontuais, dois Pipes incidentes distintos, elevação, estado e ajuste. Declare montante e jusante por UID do trecho ou ID GIS não ambíguo. Para uma divisão intermediária nova, use `PORTA_A` e `PORTA_B` nos campos mapeados para declarar os lados do Pipe, conforme sua posição original. |
| Pump | A mesma verificação de orientação e uma referência explícita à definição de bomba do modelo de destino. Confirme a definição e a sucção no WaterGEMS. |
| Registro de bloqueio | `isolation_valves` associa a válvula ao Pipe declarado e exporta a posição fracionária. A válvula não ocupa o nó das extremidades. |
| Booster | Inventário e composição referenciada. Mapeie um JSON com `bombas`, `pipes`, `succao` e `recalque`, por `WNA_UID` dos elementos preparados. `nos` e `dispositivos` são listas opcionais. As bombas e Pipes são preparados por suas respectivas categorias, com os vínculos explícitos. |
| Outros ou incompletos | Camadas `inventario_*` para conferência. Setores e zonas ficam em `referencia_*` e são auxiliares. |

As relações de montante, jusante e Pipe associado acompanham o pacote em `WNA_VINCULOS_EQUIPAMENTOS.csv`. **Cobertura por categoria** e `WNA_COBERTURA_MODELBUILDER.csv` mostram inventário, preparados, pendências e exportados. Os Pipes materializados são contados por segmento, enquanto o inventário de redes conta as feições ou partes de entrada. O escopo completo conserva os Pipes isolados e os previstos como inativos. Uma exclusão por inconsistência crítica exige a opção de exportação parcial. Os Selection Sets preservam as chaves originais dos membros que foram materializados em nós diferentes ou em segmentos derivados.

As camadas de importação são preparações GIS. A configuração exata do ModelBuilder, a orientação efetiva dos dispositivos e a sincronização precisam ser conferidas na versão WaterGEMS usada. O pacote indica que a validação nativa está pendente, inclusive para 2020 e 2026. [Importar dados externos](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0057220) · [Orientação e Downstream Pipe](https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0058900) · [Representação das ventosas](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015232) · [Válvulas de isolamento](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0058036).
