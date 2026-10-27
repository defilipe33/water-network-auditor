# Investigação operacional e filtros — 1.5.0

O fluxo é **filtrar → selecionar → localizar → analisar → salvar → próxima**.
O diagnóstico automático, a interpretação do usuário e uma eventual proposta são
registros distintos. Nenhuma dessas ações escreve no WaterGEMS ou no cadastro GIS.

## Resultado da análise

O formulário ao lado da ocorrência oferece PENDENTE, CONFIGURAÇÃO APARENTEMENTE
ADEQUADA, MANTER CONFIGURAÇÃO ATUAL, CORREÇÃO NECESSÁRIA, NECESSITA INVESTIGAÇÃO
ADICIONAL e NÃO SE APLICA. Escolher um resultado é suficiente para salvar, mesmo
sem observação. Também é possível salvar só uma observação, sem escolher resultado.
Motivos são opcionais, editáveis e incluem separações intencionais, pontas secas,
questões cadastrais e necessidade de conferência. Não se exige responsável,
documento, aprovação, assinatura, fonte ou evidência. Não há vinculação com ART.

SALVAR e Salvar e próxima ficam fora da área rolável do formulário. A segunda ação
respeita a próxima ocorrência da lista filtrada, sem saltar um caso quando o atual
sai da fila. Salvar novamente sem alterações não duplica o registro. Alterações
pendentes continuam protegidas por Salvar/Descartar/Cancelar, inclusive ao encerrar.

O resultado é interpretação investigativa, nunca comprovação hidráulica. MANTER
CONFIGURAÇÃO ATUAL não cria intervenção; CORREÇÃO NECESSÁRIA também não cria uma
proposta automaticamente. Propostas continuam opcionais em HISTÓRICO E PROPOSTAS.
O formulário formal antigo não é disponibilizado no fluxo principal; seus dados,
anexos e APIs de compatibilidade permanecem conservados.

A fila inicial mostra pendências, análises em curso e casos que necessitam
conferência. Resultados de manutenção, adequação, correção e não aplicabilidade saem
dessa fila. Use Todos os casos ou o filtro de resultado para consultá-los. Selecionar
um resultado já analisado muda explicitamente a fila para Todos. Uma anotação antiga
não é convertida automaticamente em resultado novo. Revisão espacial e histórica
administrativa são apresentadas como contextos anteriores, não como o novo resultado.

## Prioridade

A prioridade anterior do diagnóstico é preservada. A sugestão nova registra regra
e motivo próprios: transições inequívocas entre regiões e referências incompletas
podem justificar investigação prioritária; proximidade e componentes distintos,
isoladamente, não tornam uma conexão ausente um defeito de prioridade alta.
Relações de fronteira recebem contexto para verificar separações intencionais.

O usuário pode escolher Alta, Média ou Baixa como prioridade de trabalho. A sugestão
original e seu critério ficam congelados no histórico da análise. A fila considera
o resultado, independentemente da prioridade. Não há herança automática entre
execuções/cenários alterados.

## Filtros genéricos

Expanda Filtros e Filtros por atributos e regiões. Selecione origem GIS/WaterGEMS,
camada ou tipo, campo, operador e valor. Os campos são descobertos nos dados da
execução. Não se pressupõe equivalência entre ID, Label, setor cadastral ou região.
Propriedades WaterGEMS mantêm tabela, cenário, alternativa e versão de origem;
Initial Settings são atributos de cenário, não estados efetivos de uma simulação.

Números têm comparações e intervalo inclusivo. Textos têm comparação exata, contém,
início/fim, lista separada por ponto e vírgula, nulo e vazio. Booleanos têm verdadeiro,
falso e nulo. Datas tipadas têm antes/depois/intervalo. IDs textuais mantêm zeros à
esquerda. Nulo, zero, vazio e campo ausente são distintos. Não há conversão silenciosa
de identificadores nem de unidades físicas: valores são os brutos da fonte; unidades
não documentadas permanecem desconhecidas.

Cada condição pode considerar pelo menos um, todos ou nenhum dos elementos daquela
origem/camada. Campo ausente ou relação não demonstrada é **indeterminado**, não falso.
Em particular, Nenhum não aprova casos só porque faltam atributos. O painel informa
quantos casos ficaram indeterminados. E/OU combinam condições por ocorrência; não
significam necessariamente que duas condições foram satisfeitas pela mesma tubulação.
Grupos permitem combinações aninhadas. Remova condições individualmente ou limpe tudo.

A lista mostra até 200 ocorrências por página; as contagens e os filtros consideram
o conjunto completo. A seleção e Salvar e próxima atravessam páginas sem saltar casos.

Os filtros não criam diagnósticos. O detalhe expansível mostra valores avaliados,
elementos e proveniência. Perspectiva, seleção compatível e filtros são preservados
ao navegar. Salvar filtros registra a árvore, fila e resultado na execução/perspectiva
exatas, para outra sessão. Alterar filtros não recalcula a rede.

## Polígonos e relações

IG_LOCAL_AREA pertence às camadas adicionais de contexto da integração. Pode estar
vazia quando nenhuma dessas camadas foi selecionada, mesmo existindo regiões na
auditoria geométrica. Nomes apresentados no diagnóstico não demonstram pertencimento.

A extensão utiliza as chaves de LOCAL_EVENTO/EVENTO_POLIGONO e os candidatos antes,
depois e fronteira do dossiê. Conserva cada polígono e a origem da relação. Antes/depois
seguem a orientação geométrica, não o escoamento. Sobreposições mantêm candidatos;
não há desempate arbitrário. Extremidade sem um lado não é interpretada como exterior.

Recuperar geometrias verificadas abre fontes disponíveis somente para leitura e
aceita polígonos cuja assinatura de origem, atributos e WKB corresponda ao registro
original. A transformação para o CRS da auditoria é explícita. Fonte ausente ou
alterada gera aviso. Dentro/intersecta/fronteira sem geometria confiável permanecem
indeterminados, com exceção de evidências geométricas já classificadas na auditoria.

Adicionar polígonos do projeto permite incluir setores, VRPs, DMCs, boosters ou outros
limites, sem nomes fixos. Conserva atributos, assinatura, CRS original/comparação e
snapshot transformado; não modifica a auditoria original. A referência espacial
validada é obrigatória. Relações Dentro/Intersecta desses filtros referem-se ao ponto
representativo do local; não afirmam que toda a tubulação está contida. Relações
entre lados/regiões usam evidências antes/depois do evento e permanecem indeterminadas
quando essas evidências não bastam.

## Persistência e compatibilidade

A primeira gravação estende o mesmo GeoPackage através de transação, após backup
completo verificado. Abrir/consultar uma base não a migra. Tabelas novas:

- IGD_OPERACIONAL_SCHEMA: versão da extensão e referência ao backup.
- IGD_ANALISES: cadeia imutável de resultados, motivos, observações, prioridades,
  assinatura técnica, execução, perspectiva, cenário, data e registro anterior.
- IGD_FILTROS: versões das configurações por investigação/perspectiva.
- IGD_AREAS_FILTRO e IGD_GEOMETRIAS_FILTRO: identidades, atributos e snapshots
  espaciais com proveniência, preservando a execução de origem.
- IGD_RELACOES_AREA: vínculos de locais/eventos com polígonos e natureza da relação.

As chaves e índices não dependem de fid. Histórico usa transações e comparação do
registro anterior para detectar gravação concorrente. Tabelas antigas e IG_LOCAL_AREA
não são reescritas. Exportações acrescentam RESULTADOS_INVESTIGATIVOS, HIST_ANALISES,
RESUMO_ANALISES e RELACOES_PARA_FILTROS, preservando as abas anteriores. GPKG guarda a
estrutura completa; SHP oferece a visão espacial, com CSVs para os dados extensos.

## Verificação manual instalada

1. Instale o ZIP e reinicie o QGIS 3.44.15. Abra uma cópia da investigação.
2. Selecione uma ocorrência e salve apenas uma observação. Reabra e confira o histórico.
3. Escolha MANTER CONFIGURAÇÃO ATUAL e um motivo de separação intencional. Não informe
   responsável ou evidência. Confira a saída da fila e a consulta em Todos.
4. Registre CORREÇÃO NECESSÁRIA sem observação; confirme que não foi criada proposta.
5. Teste filtros de material, intervalo numérico, nulo, lista de IDs e atributo próprio.
   Combine setores e outro limite com E/OU e teste qualquer/todos/nenhum.
6. Recupere limites por assinatura ou adicione uma camada em outro CRS; confira o mapa
   e os atributos que atenderam ao filtro. Cancelar não deve alterar o contexto.
7. Salve filtros, feche e reabra o QGIS; confira a execução e perspectiva corretas.
8. Exporte GPKG/SHP/XLSX. Verifique também o XLSX no Excel desktop. Teste janela de
   notebook, rolagem e botões fixos; teste Salvar/Descartar/Cancelar no encerramento.

Testes instalados pela API Qt não substituem a aceitação humana da ergonomia. Não
se declara validação hidráulica pelo resultado escolhido. Contextos antigos sem
atributos tipados ou sem fontes disponíveis podem exigir referência adicional.
