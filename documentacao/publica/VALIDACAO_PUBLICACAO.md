# Validação da distribuição pública

Ambiente: Windows 64 bits, QGIS 3.44.15-Solothurn / Python 3.12,
NetworkX 3.7 e openpyxl 3.1.5, conforme o runtime examinado.

## Verificações executadas

| Verificação | Resultado |
|---|---|
| Suíte pública em cópia limpa do índice, sem cadastros ou modelos locais | 419 testes aprovados |
| Testes anteriores da aplicação | Preservados; fixtures continuam sintéticas |
| Imports dos dois pontos de entrada no Python do QGIS | Aprovados |
| Recurso SVG e estrutura do complemento | Aprovados |
| ZIP construído somente com a árvore publicável | Íntegro, 57 arquivos verificados por SHA256 |
| Sintaxe Python | Compilação aprovada |
| Índice preparado para publicação | Conteúdo e caminhos revisados, sem achados pendentes |
| Proteções do gitignore | Dados, modelos, resultados e ensaios privados excluídos |
| Roadmaps e algoritmos protegidos | Hashes locais preservados |

A suíte anterior à publicação possuía 414 testes. Foram acrescentados cinco testes
do verificador de publicação. Um identificador numérico usado como exemplo em uma
fixture foi substituído por valor inventado equivalente, sem alterar regras de
normalização, processamento ou expectativa de precisão. A versão original dessa
fixture foi preservada no histórico técnico local não publicado.

A documentação pública apresenta contratos e histórico genérico. Os documentos
operacionais, configurações, cadastros e ensaios reais originais continuam locais.
Os dois PDFs de planejamento foram inspecionados e são publicados sem modificação;
são registros históricos, não uma declaração de conclusão de todas as suas frentes.

A revisão de publicação combina inspeção de conteúdo, política de caminhos, filtros
de credenciais, tamanho e hashes de PDFs revisados. O script é uma barreira adicional,
não uma garantia de que detecção automática substitui o julgamento humano.

## Limites da validação

Não foi repetida a aceitação visual desktop apenas para publicar os fontes: as
alterações da entrega são documentação, manutenção e fixtures de segurança. A
validação anterior por API em perfil QGIS isolado permanece parcial quanto ao
encerramento normal do processo e à aceitação por cliques. Excel e WaterGEMS
desktop também não foram revalidados nesta preparação.

O workflow GitHub faz verificações de repositório, sintaxe, política e pacote.
Não apresenta suas verificações como substitutas da suíte completa PyQGIS.
Não foi escolhida licença para o projeto. Dependências e referência externa
estão identificadas em THIRD_PARTY_NOTICES.md.
