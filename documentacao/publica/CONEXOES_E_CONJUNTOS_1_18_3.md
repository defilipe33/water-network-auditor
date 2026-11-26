# Revisão de conexões e conjuntos para WaterGEMS

## Revisar uma conexão no QGIS

Em **Investigar minha rede → Analisar conectividade → Conexões e continuidade da rede**, escolha uma candidata e use **Revisar conexão selecionada**. Confira as posições e a distância, escolha o veredito e o acompanhamento e salve. A observação é opcional. **Verificado** indica uma revisão concluída pelo usuário. O acompanhamento padrão para um veredito indeterminado é **Necessita confirmação**.

Na revisão sequencial, **Salvar decisão e avançar** grava a revisão, guarda o rascunho e move a fila. Para retomar, reabra a execução e use **Retomar revisão salva**. As tabelas identificam o acompanhamento atual e o que constava na fotografia da execução. A participação modifica o rascunho. Fixe ou execute a hipótese para aplicar as alterações à topologia.

## Verificar conexões repetidas

Abra uma execução e use **Verificar conexões repetidas**. O relatório compara a identidade técnica das partes, a posição longitudinal em metros, a distância entre as posições de referência, o tipo, a natureza e eventual direção. A ordem A–B pode ser invertida em ligações sem direção. Candidatas em Pipes diferentes continuam distintas mesmo se tiverem a mesma localização. O relatório separa equivalências, conflitos, vínculos com a candidata original e revisões da mesma relação.

Use duplo clique para localizar o par e o menu contextual para revisar os registros. Para duas relações declaradas equivalentes, escolha a principal. O complemento registra uma revisão de substituição e conserva a revisão anterior. Uma hipótese histórica continua apontando para suas revisões fixadas. Em um conflito de vereditos, confira a participação da relação principal no rascunho.

Ao criar manualmente uma ligação que corresponde a outra, abra o registro encontrado ou explique a distinção técnica. Referências indisponíveis ou incompletas aparecem como inconclusivas na auditoria.

## Criar e exportar conjuntos

Abra **Investigar minha rede → Redes estruturantes → Conjuntos para WaterGEMS**, selecione a regra de atividade da exportação e crie um conjunto. Também é possível começar no menu contextual de um resultado estrutural ou na prévia do cadastro completo. Escolha corredores, blocos, Pipes de intervenções, conexões aplicadas, elementos alcançáveis de uma origem, áreas, isolados, divididos, inativos ou feições selecionadas. O filtro por atributo procura o valor exato na prévia.

Um conjunto guarda o nome, a categoria, a subpasta, a revisão, a execução, a assinatura da topologia exportável e as identidades dos membros. O mesmo Pipe pode participar de vários conjuntos. Uma conexão aplicada reúne os Pipes que tocam suas portas e a Junction que os representa. Um Pipe dividido é representado pelos segmentos materializados. A associação de áreas por interseção é espacial.

O menu contextual permite consultar membros e revisões, editar, arquivar, recuperar e exportar um conjunto. O duplo clique aproxima os membros com correspondência. Em outra execução, confira os membros preservados, os novos segmentos de divisões verificáveis, os ausentes e os ambíguos antes de salvar uma nova composição. O complemento verifica divisões pelo intervalo da mesma parte. A revisão anterior continua disponível.

### Arquivos e atributos

| Arquivo ou campo | Informação |
|---|---|
| `pipes` e `junctions` | Geometrias, atributos cadastrais e esquema de preparação `WNA_ESQUEMA` |
| `WNA_UID` | Chave técnica textual de 24 caracteres do segmento ou da Junction |
| `WNA_ORIG_UID`, `WNA_ID_GIS` | Identidade física de origem e identificador cadastral, quando conhecidos |
| `WNA_LABEL` | Label previsto a partir de `WNA_UID` |
| `WNA_ATIVO` | Atividade pretendida na exportação |
| `WNA_CORREDOR`, `WNA_BLOCO`, `WNA_INTERV` | Associação principal por categoria na exportação, escolhida pela ordem de nome e UUID entre os conjuntos exportados |
| `WNA_CONJUNTOS` | Catálogo e metadados de cada conjunto |
| `WNA_ELEMENTO_CONJUNTO` | Uma linha por vínculo elemento–conjunto, com tipo, revisão, execução e procedência |
| `validacao.json` | Escopo, contagens, pendências, regras e dicionário DBF para Shapefile |
| `MINUTAS_QUERIES` | Expressões textuais agrupadas por conjunto, tipo e lote, com índice de contagens |

O catálogo e a tabela de vínculos acompanham GeoPackage e Shapefile em CSV. No GeoPackage, também estão disponíveis como tabelas de atributos. No pacote de seleção, Junctions necessárias aos Pipes podem acompanhar a geometria como contexto. A participação no conjunto é a da tabela de vínculos. O cadastro completo continua disponível para exportar redes isoladas e Pipes fora da hipótese.

## Criar o Selection Set em uma cópia do WaterGEMS

1. Confira a revisão e a execução em `validacao.json`. Abra uma cópia do modelo correspondente.
2. Crie um User Data Extension **de texto** para `WNA_UID` em cada tipo de elemento e mapeie explicitamente o campo no ModelBuilder. Use a correspondência unívoca que for válida no modelo de destino. Trate duplicidades, ausências e associações incorretas antes de executar as consultas. [Bentley sobre User Data Extensions](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015506).
3. Compare os `WNA_UID` e os tipos da FlexTable exportada com `WNA_ELEMENTO_CONJUNTO.csv`. Abra uma Query do tipo correto, selecione o campo que o Query Builder efetivamente oferece, valide a minuta e confira o total de cada lote. [Procedimento Bentley de seleção a partir de planilha](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0059255).
4. Crie um Selection Set estático a partir do primeiro lote validado. Use **Add to Selection Set** para acrescentar os seguintes, quando disponível. Compare os elementos distintos com a tabela completa e organize a pasta conforme a categoria. [Criação de Selection Set](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0015896), [sintaxe IN e inclusão em conjuntos](https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0014413).

As expressões levam o estado **Pendente no modelo de destino**. O pacote prepara o trabalho no QGIS. A criação, validação e atualização do conjunto nativo dependem do modelo WaterGEMS e da correspondência conferida nessa instalação. Equipamentos continuam no inventário cadastral. A composição selecionável desta versão materializa Pipes e Junctions. A revisão e a exportação operam nos arquivos próprios do complemento e nos produtos gerados.
