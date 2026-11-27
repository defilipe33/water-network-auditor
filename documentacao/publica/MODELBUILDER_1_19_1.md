# Preparar pacotes ModelBuilder na versão 1.19.1

## Diagnóstico das falhas da versão 1.19.0

O exportador tratava a ausência de qualquer ponta e o retorno ao mesmo nó com a mesma exceção. O ensaio sintético reproduziu a interrupção com uma linha fechada. A mensagem original do projeto Registro é compatível com várias causas e não permite determinar qual ocorreu naquele Pipe. O diagnóstico por elemento agora registra os nós, as coordenadas das pontas, a camada, o ID GIS, o Pipe físico, o segmento e as relações de conectividade disponíveis.

O inventário cadastral preservava atributos PyQGIS e tentava gravá-los diretamente como JSON. Um campo de data real pode chegar como `QDate`. A preparação comum do pacote converte datas e horários para ISO 8601, preserva o deslocamento UTC quando disponível e mantém números, nulos e estruturas aninhadas. Valores binários são identificados como hexadecimal. Um tipo indisponível fica nulo e aparece no registro de serialização do pacote com seu campo e tipo. A mesma representação é usada ao gravar os atributos originais de Selection Sets, inventário, operações, equipamentos e pacotes ModelBuilder.

## Exportar no QGIS

1. Em **Investigar minha rede**, selecione **Exportar modelo para WaterGEMS** e abra a execução de conectividade desejada.
2. Em **Origem e escopo**, escolha o cadastro completo, a hipótese, a rede alcançável pelas origens escolhidas ou um recorte por corredores, blocos, áreas ou conjuntos. Em **Escolher elementos do escopo**, as marcas são preservadas quando você pesquisa. **Selecionar itens filtrados** atua sobre os itens mostrados e **Selecionar todos** atua sobre o universo da lista.
3. Em **Elementos e atributos**, informe o destino, a estratégia de criação ou atualização, os tipos necessários, os campos e as unidades. Salve o perfil nesta etapa para recuperar as escolhas depois, mesmo sem gerar um pacote.
4. Em **Atividade e conjuntos**, confira as regras de atividade pretendida e os conjuntos associados. A atividade registrada no pacote serve à preparação e à conferência.
5. Em **Validação e exportação**, clique em **Validar**. Confira os erros críticos e as pendências hidráulicas ou cadastrais. Use duplo clique para localizar uma ocorrência com geometria. Use o menu de contexto para consultar as relações e revisar a execução de conectividade.
6. Escolha GeoPackage, Shapefile ou CSV e clique em **Exportar pacote**. Ao mudar escolhas que afetam a validação, valide novamente. Os pacotes publicados pelo assistente aparecem no histórico.

O cadastro completo pode incluir redes isoladas e segmentos fora da hipótese. Regiões sem origem topológica permanecem no escopo completo e são identificadas em indicadores próprios. O recorte **Rede alcançável pelas origens selecionadas** tem outro escopo e deve ser escolhido explicitamente.

## Resolver pendências de topologia e diâmetro

As pendências distinguem nó inicial indisponível, nó final indisponível, duas pontas diferentes atribuídas ao mesmo nó, anel retornando ao mesmo nó e geometria vazia, degenerada ou com intervalo inválido. Também são apresentados nós ou pontas deslocados, conforme o caso. Duas identidades nodais distintas na mesma coordenada são sinalizadas para conferência das referências explícitas de Start e Stop.

Com a opção de segmentação habilitada, um anel fechado, simples e com a ponta coincidente com seu nó pode ser dividido no ponto médio do comprimento geométrico. O pacote preserva o comprimento geométrico total e a vinculação ao Pipe de origem. Os novos segmentos recebem identidades próprias, guardam o UID do segmento anterior e herdam a associação aos conjuntos selecionados. A intervenção existe somente na exportação. A distribuição do comprimento hidráulico cadastrado pelos segmentos exige dados compatíveis.

Quando restarem problemas críticos, revise a conectividade ou escolha explicitamente **Exportar somente elementos válidos**. O manifesto marca o pacote como `EXPORTACAO_PARCIAL` e os arquivos de pendências e associações identificam as exclusões. Se a gravação falhar, a pasta temporária não é apresentada como um pacote concluído.

**Diâmetros por fonte** e `WNA_DIAMETROS_POR_FONTE.csv` separam fonte sem campo mapeado, unidade desconhecida, valor vazio e valor inválido. As quantidades são de feições lidas por fonte. A prévia informa também o número de segmentos sem diâmetro. Para ajustar a configuração, volte ao **Modelo GIS** e revise o campo e a unidade da fonte. Os segmentos derivados reaproveitam o diâmetro convertido do Pipe correspondente. A exportação conserva o atributo vazio quando o valor não é confiável.

## Identidade e Labels

`WNA_UID` continua sendo a chave técnica. O registro de Labels no GeoPackage complementar é aditivo e recebe uma cópia de segurança antes da primeira criação. Ele reserva Labels sem distinção entre maiúsculas e minúsculas. Pode preservar um Label cadastral elegível de até 32 caracteres ou gerar `P-000001`, `J-000001`, `R-000001` e `T-000001`. Os prefixos são configuráveis e uma reserva anterior continua valendo após alterar o prefixo. `MB_INICIO` e `MB_FIM` referenciam exatamente os Labels nodais do pacote. `MB_TIPO_A` e `MB_TIPO_B` indicam os tipos nodais preparados.

Para atualizar um modelo baseado na 1.19.0, selecione o pacote de referência antes de reservar novas identidades. Uma divergência de Label entre o registro local e a referência interrompe a preparação da atualização para conferência. Os arquivos dos conjuntos incluem o Label preparado para consulta e mantêm os vínculos por `WNA_UID`; a importação ou criação de um Selection Set nativo requer verificação no destino.

## Tipos hidráulicos

| Tipo | Tratamento do pacote |
| --- | --- |
| Junction | Ocupa o nó topológico; elevação ausente fica registrada como pendência hidráulica. |
| Reservoir | Ocupa o mesmo nó quando há vínculo explícito, posição compatível e carga mapeada. |
| Tank | Ocupa o mesmo nó quando há vínculo explícito, posição compatível, base, níveis coerentes e diâmetro do tanque cilíndrico. |
| Hydrant | Mantido no inventário até validar porta, elevação e configuração do ramal, quando aplicável. |
| PRV, PSV, TCV e FCV | Mantidas no inventário; a preparação nativa exige portas e orientação explícitas, propriedades do tipo e verificação na versão de destino. |
| Bomba e booster | A preparação depende de sucção, recalque e dados da bomba; o booster precisa de composição declarada. |
| Registro de bloqueio | Mantido no inventário; requer Pipe associado, posição e estado explícitos. |

Um Reservoir ou Tank aceito substitui a Junction daquele nó no pacote. Disputa entre equipamentos, falta de parâmetros ou localização incompatível ficam registradas para revisão. O QGIS valida a preparação GIS. A configuração, a atualização sem duplicação, as associações e o comportamento no WaterGEMS exigem ensaio nativo na versão de destino. Os pacotes não escrevem nos arquivos WaterGEMS.

As representações nativas consultadas para preparar esse contrato estão na documentação Bentley. [Hydrant e ramal lateral](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0057933), [reguladoras de pressão](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0016954), [orientação de FCV](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0016654), [válvulas de isolamento associadas a Pipes](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0016596).
