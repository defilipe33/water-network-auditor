# Validar referência espacial do WaterGEMS — versão 1.12.1

Histórico dos ensaios iniciais: [validação da versão 1.2.0](VALIDACAO_ASSISTENTE_1_2.md).

Na aba **CRS e unidades**, use **VALIDAR REFERÊNCIA ESPACIAL DO WATERGEMS…**.
Abra ou crie antes uma base topológica e uma auditoria geométrica. A extração e os
resultados anteriores continuam utilizáveis sem CRS; o assistente não escreve nas fontes.

## Fluxo atual — 1.12.1

1. **Identificar os dados:** leitura automática de fontes, cenário, CRSs e referências anteriores. Esta página pode ser apenas consultada quando os dados já estão selecionados.
2. **Conferir correspondências:** tabela de campos sugeridos e exemplos; alterar escolhas quando necessário, sem checkbox de aceite. Empates continuam explícitos.
3. **Verificar compatibilidade espacial:** comparar hipóteses, geometrias e controles. O resumo mostra resultado e próxima ação; estatísticas completas e Junctions ficam nas opções avançadas.
4. **Salvar e continuar:** nova versão íntegra, atualização da configuração e fechamento automático, sem responsável ou aprovação formal.

O [guia de refinamento e capturas reais](REFINAMENTO_ESPACIAL_1_12_1.md) descreve o fluxo e as pendências técnicas. Documentos e observações são opcionais. A ausência de referência confiável de CRS continua bloqueando a validação; ajuste geométrico não prova datum.

Detecção, análise de campos, comparação e gravação executam fora da thread da interface.
Cancelar solicita interrupção no próximo ponto seguro. A troca de contexto e a saída do
complemento ficam bloqueadas enquanto o trabalho estiver ativo. Em falha não é publicada
uma versão parcial; intermediários podem permanecer na pasta técnica para diagnóstico.

## O que foi encontrado no SQLite

Os esquemas reais examinados apresentam `IdahoDataSet.HMIDataSetGeometrySpatialReference`
e `HMIDataSetGeometrySpatialReferenceConversionFactor`. O segundo tem valor zero nos
modelos examinados e **não foi interpretado como fator dos valores WKB**.

Em um dos modelos, `IdahoDataSet.HmiModelCoordinateReference` contém JSON com
`horizontalCRS`, referência EPSG, unidade e projeção. O leitor usa somente a raiz
horizontal: códigos aninhados de datum/elipsoide não são códigos de CRS. Confere o
código com o catálogo QGIS, a zona/hemisfério declarados quando presentes e a unidade.
O outro modelo não forneceu definição interpretável nos campos observados.

Tabela, coluna, valor bruto, interpretação, confiabilidade, versão de esquema e hash
ficam na evidência. Campos desconhecidos são candidatos não interpretados. JSON inválido
ou definições conflitantes bloqueiam a validação. Ausência gera a mensagem
**CRS NÃO IDENTIFICADO NOS METADADOS WATERGEMS**; não gera um EPSG presumido.

O leitor não pretende ser um decodificador universal de todas as versões Bentley.
Novos formatos exigem mapeamento documentado e testes. O leitor WKB consultado no
Model Builder Composer decodifica coordenadas; ele não comprova por si só CRS/unidade.

## Quatro conceitos distintos

| Conceito | Evidência |
|---|---|
| Unidade exibida pelo WaterGEMS | Observação documentada/controle; pode permanecer desconhecida |
| Unidade dos valores WKB brutos | Metadado confiável ou hipótese diferenciada pela comparação |
| Unidade do CRS | Definição espacial declarada e interpretada pelo QGIS |
| Fator de conversão | Hipótese testada e registrada, sem ajuste arbitrário |

As fontes GIS são transformadas explicitamente para o CRS projetado métrico da
comparação. Ficam registrados WKT de origem/destino e pipeline instanciado pelo QGIS.
Se o CRS WaterGEMS declarado diferir do CRS de comparação, selecione o CRS declarado
e reprojete o GIS para ele. Não há ajuste livre de rotação, translação ou escala.
Modelos com referência não métrica ou que exijam outra interpretação de coordenadas
WaterGEMS permanecem pendentes; não são forçados a coincidir.

## Critérios conservadores

- Tolerância de vértices explícita, inicialmente herdada da configuração existente;
  nunca é ampliada para melhorar contagens. Justifique-a pela precisão dos cadastros.
- Chave única nos dois ambientes; repetições entre camadas também impedem unicidade.
- Hipótese vencedora única, com pelo menos três pares compatíveis (ou todos em modelos
  com menos de três tubulações) e concordância mínima de 95% dos pares com vértices
  comparáveis. Os 95% são uma salvaguarda de implementação, não norma de engenharia;
  divergências remanescentes continuam reportadas e precisam de análise.
- Controles importados devem corresponder ao contexto exato. ID ausente, Label alterado,
  falta de geometria ou desvio incompatível com a precisão bloqueiam a confirmação.
- Para coordenadas arredondadas a duas casas, o limite é 0,005 m por eixo, mais
  margem numérica de 1e-8 m. Uma Junction isolada não valida a rede inteira.
- Metadados ou evidência documental sustentam o datum. Coincidência de geometrias sozinha
  não o comprova. `APTO_PARA_CONFIRMACAO` é diferente de `VALIDADO`.
- A verificação técnica e a proveniência são exigidas; responsável, aprovação formal e anexos não são. Conectividade hidráulica não é deduzida da validação espacial.

Contagens cadastrais podem se sobrepor: um registro nulo também pode não ser encontrado.
As estatísticas de erro usam somente pares com quantidade de vértices comparável; os
demais continuam classificados como inconsistentes no relatório. A média e os percentis
são calculados sobre os desvios individuais dos vértices, não sobre máximos por tubo.

## Evidência e versão

A persistência existente gera nova base, UUID, origem e assinatura. `WB_EVIDENCIA`
contém JSON estruturado, com chave estrangeira explícita para `WB_BASE`. Também é
gerado `EVIDENCIA_REFERENCIA.json` na pasta técnica. A evidência registra contexto,
cenário/alternativas, assinaturas, critérios, regras, estatísticas, amostras, controles,
fontes GIS e operações CRS. Documentos anexados são copiados e verificados por hash.

Na reabertura, os dados confirmados são recuperados. A reutilização do assistente sem
comparação completa exige contexto WaterGEMS e assinaturas dos arquivos GIS iguais.
Fontes sem assinatura reproduzível de arquivo não habilitam esse atalho. Bases legadas
continuam legíveis; evidências antigas sem contexto suficiente exigem nova verificação.
Snapshot desaparecido não impede consulta; metadados já persistidos continuam disponíveis.

As fontes originais são abertas somente para leitura. Um WAL não vazio impede usar
um arquivo como substituto de snapshot validado apenas pelo hash do arquivo principal.

## Roteiro de aceitação manual

1. Instale o ZIP atualizado em perfil de teste e reinicie o QGIS.
2. Em notebook e escala habitual, abra a base e o assistente. Confira sete etapas,
   rolagem, acesso aos botões e redimensionamento.
3. Confira metadados e a distinção entre CRS da camada, projeto, auditoria e comparação.
4. Examine recomendações, empates, nulos, zeros e IDs com zeros à esquerda. Confirme
   somente colunas verificadas; teste seleção incorreta e ausência de correspondência.
5. Compare as duas unidades; confira estatísticas e divergências no mapa. Adicione
   controles distribuídos quando houver observações independentes disponíveis.
6. Cancele durante análise e confirme que nenhum resultado foi publicado. Reabra e repita.
7. Teste ausência de metadados/documento, contexto incompatível e controle alterado.
   A consulta topológica deve continuar disponível e a integração espacial bloqueada.
8. Aprove tecnicamente, salve em arquivo novo e confira UUID, histórico, JSON e anexos.
9. Feche o QGIS e reabra: verifique recuperação e reutilização, sem comparação completa.
   Altere uma fonte de teste e confirme a exigência de nova validação.

Ensaios pela API Qt em perfil desktop isolado não substituem aceitação humana por
cliques, conferência dos controles no WaterGEMS e testes físicos de múltiplos monitores.
Dados e relatórios reais ficam somente no ambiente local, fora do GitHub.
