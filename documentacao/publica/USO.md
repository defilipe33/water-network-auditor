# Instalação e operação

Gerar o ZIP com `testes/empacotar_plugin.py` e instalar pelo gerenciador do QGIS,
conforme o README principal. Os fontes canônicos são incorporados em `_biblioteca`
com manifesto SHA256; não há uma segunda implementação dos algoritmos no plugin.

O menu e o botão inicializam a janela geométrica e permitem configurar a pasta de
trabalho. O catálogo dessa pasta pode recuperar auditorias GIS, bases WaterGEMS e
investigações integradas. Arquivos e subpastas por projeto são sugestões editáveis.

## Auditoria geométrica

Selecione redes e limites já carregados. Para cada origem, escolha identificador;
para polígonos, escolha também exibição e modo TRANSICAO/PERIMETRO. A exibição
pode ser o próprio ID. Nome disponível não substitui automaticamente sua escolha.
Tolerância geométrica, continuidade, busca e extensão máxima do agrupamento são
parâmetros independentes, medidos em CRS projetado métrico adequado.

O comando de atualizar a lista de camadas não refaz resultados. Após conclusão,
entradas ficam protegidas. Utilize os quatro modos explícitos:

| Modo | Ação |
|---|---|
| Nova auditoria | Detectar eventos a partir de entradas selecionadas |
| Continuar auditoria | Recuperar resultados e revisões sem recalcular |
| Regerar locais | Reagrupar os eventos existentes com parâmetros novos |
| Reprocessar auditoria | Alterar entradas/regras geométricas e gerar outra versão |

Na inspeção, consultar eventos, tubulações e áreas expansíveis; usar seleção
cruzada e zoom explícito. O sentido antes/depois é geométrico, não hidráulico.

## WaterGEMS e investigação

Se o índice estiver vazio ou indisponível, consulte a [recuperação do catálogo](RECUPERACAO_CATALOGO.md).
Não é necessário apagar o arquivo de zero bytes antes de atualizar o complemento.

Use o [assistente de validação espacial](VALIDACAO_ESPACIAL.md) na aba CRS e unidades.
A detecção precede qualquer informação manual. Confirme as colunas sugeridas,
examine unidades e geometrias e aprove somente com evidências suficientes.

Consulte o [guia de inspeção, telas, CRS/unidades e correspondência GIS × Label](USABILIDADE_CRS.md)
para o novo assistente e o roteiro de conferência em notebook.

Usar ANALISAR COM WATERGEMS somente sobre uma auditoria concluída. A configuração
pendente deve ser executada, descartada conscientemente ou mantida por cancelamento.
Revisões não salvas utilizam Salvar/Descartar/Cancelar.

Selecionar SQLite salvo, cenário e perspectiva, ou abrir uma base já persistida.
Informar CRS, fator bruto→metro e evidência antes de análises espaciais. Sem comprovação,
a consulta topológica continua disponível; a integração espacial é bloqueada.

Mapear explicitamente o campo GIS confrontado com Label WG. A ferramenta verifica
unicidade entre todas as fontes escolhidas e compatibilidade geométrica. Registrar
as pendências em vez de selecionar arbitrariamente candidatos.

Publicar uma investigação em arquivo novo. Selecionar um diagnóstico para consultar
resumo, elementos, mapa e evidências. A seleção não impõe zoom. Detalhes técnicos
ficam expansíveis. Registrar decisões e propostas no contexto da perspectiva analisada.

Fechar e reabrir a investigação pelo catálogo conserva históricos. Atualizar a base
WaterGEMS cria outra versão; não altera silenciosamente as investigações anteriores.
Arquivos movidos podem ser relocalizados por UUID, sem depender de seus nomes.

## Exportações

GPKG conserva a estrutura completa. SHP é uma visão simplificada com campos DBF
compatíveis e tabelas auxiliares; XLSX permite análise e detalhamento expansível.
Escolher formatos e destinos pelos controles existentes. Reimportar e conferir CRS,
chaves, vínculos e avisos. Nenhuma saída é uma instrução automática de intervenção.
